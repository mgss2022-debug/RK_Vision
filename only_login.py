from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
import pytesseract
from PIL import Image, ImageFilter, ImageEnhance
import time
import io
import os

# ── Tesseract Path (Linux / GitHub Actions) ────────────────────
pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

# ── Your CGM Login Details ─────────────────────────────────────
USERNAME = os.environ.get("CGM_USERNAME", "STML3601079810")
PASSWORD = os.environ.get("CGM_PASSWORD", "Mbk@2009")
MOBILE   = os.environ.get("CGM_MOBILE",   "9825028693")

# ── Captcha Solver (Pillow only — no cv2/numpy) ─────────────────
def solve_captcha(driver):
    try:
        time.sleep(2)

        captcha_info = driver.execute_script("""
            var img = document.getElementById('imgCaptcha');
            if (!img) return null;
            var rect = img.getBoundingClientRect();
            return { x: rect.left, y: rect.top, width: rect.width, height: rect.height };
        """)

        if not captcha_info or captcha_info['width'] == 0:
            print("⚠️ Captcha not visible")
            return ""

        png = driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(png))

        dpr = driver.execute_script("return window.devicePixelRatio || 1;")
        x = int(captcha_info['x'] * dpr)
        y = int(captcha_info['y'] * dpr)
        w = int(captcha_info['width'] * dpr)
        h = int(captcha_info['height'] * dpr)

        captcha_img = img.crop((x, y, x + w, y + h))

        # Scale up 3x for better OCR accuracy
        new_w = captcha_img.width * 3
        new_h = captcha_img.height * 3
        captcha_img = captcha_img.resize((new_w, new_h), Image.LANCZOS)

        # Grayscale → contrast → sharpen → threshold → denoise
        captcha_img = captcha_img.convert("L")
        captcha_img = ImageEnhance.Contrast(captcha_img).enhance(2.5)
        captcha_img = captcha_img.filter(ImageFilter.SHARPEN)
        captcha_img = captcha_img.point(lambda p: 255 if p > 140 else 0)
        captcha_img = captcha_img.filter(ImageFilter.MedianFilter(size=3))

        config = '--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
        result = pytesseract.image_to_string(captcha_img, config=config)
        return result.strip().replace(" ", "").replace("\n", "")

    except Exception as e:
        print(f"❌ Captcha error: {e}")
        return ""

# ── Safe Fill ──────────────────────────────────────────────────
def safe_fill(driver, element_id, value):
    try:
        driver.execute_script(f"""
            var el = document.getElementById('{element_id}');
            el.value = '';
            el.value = '{value}';
        """)
        return True
    except Exception as e:
        print(f"❌ Failed to fill {element_id}: {e}")
        return False

# ── Refresh Captcha ────────────────────────────────────────────
def refresh_captcha(driver):
    try:
        driver.execute_script("""
            var img = document.getElementById('imgCaptcha');
            var src = img.src.split('?')[0];
            img.src = src + '?' + new Date().getTime();
        """)
        time.sleep(2)
        print("🔄 Captcha refreshed")
    except Exception as e:
        print(f"⚠️ Captcha refresh error: {e}")

# ── Main Login ─────────────────────────────────────────────────
def login():
    print("🚀 RK_Vision Starting...")

    # ── Chrome Options for GitHub Actions ─────────────────────
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-setuid-sandbox")
    options.add_experimental_option("prefs", {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.password_manager_leak_detection": False
    })

    # GitHub Actions uses chromedriver directly
    service = Service("/usr/bin/chromedriver")
    driver  = webdriver.Chrome(service=service, options=options)
    driver.set_window_size(1920, 1080)

    driver.get("https://cgmatr.ncode.in/cgm-ilms/login.aspx")
    print("✅ Portal opened")

    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "txtLoginUserName"))
    )
    time.sleep(3)

    for attempt in range(1, 6):
        print(f"\n🔄 Attempt {attempt}/5...")
        try:
            safe_fill(driver, "txtLoginUserName", USERNAME)
            print("✅ Username entered")

            safe_fill(driver, "txtLoginPassword", PASSWORD)
            print("✅ Password entered")

            safe_fill(driver, "MobileNumber", MOBILE)
            print("✅ Mobile entered")

            solved = solve_captcha(driver)
            print(f"🔐 Captcha solved: '{solved}'")

            if not solved or len(solved) < 3:
                print("⚠️ Captcha unclear, refreshing...")
                refresh_captcha(driver)
                time.sleep(2)
                continue

            safe_fill(driver, "txtCaptcha", solved)
            print("✅ Captcha entered")

            driver.execute_script("document.getElementById('LoginButton').click();")
            print("✅ Login clicked")

            time.sleep(5)

            current_url = driver.current_url.lower()
            if "login" not in current_url:
                print(f"\n🎉 LOGIN SUCCESSFUL!")
                print(f"📍 URL: {driver.current_url}")
                return driver

            try:
                error_msg = driver.execute_script("""
                    var els = document.getElementsByClassName('alert-danger');
                    if (els.length > 0) return els[0].innerText;
                    return '';
                """)
                if error_msg:
                    print(f"❌ Portal error: {error_msg.strip()}")
                else:
                    print("❌ Still on login page — captcha may be wrong")
            except:
                print("❌ Still on login page")

            driver.get("https://cgmatr.ncode.in/cgm-ilms/login.aspx")
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "txtLoginUserName"))
            )
            time.sleep(3)

        except Exception as e:
            print(f"⚠️ Unexpected error: {e}")
            driver.get("https://cgmatr.ncode.in/cgm-ilms/login.aspx")
            time.sleep(3)

    print("\n❌ All 5 attempts failed.")
    return None

# ── Run ────────────────────────────────────────────────────────
if __name__ == "__main__":
    driver = login()
    if driver:
        print("\n✅ Ready for next steps!")
        driver.quit()
