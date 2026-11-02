# بردن پروژه روی GitHub (چند کلیک، بدون کدنویسی)

مخزن GitHub از داخل این محیط ساخته نشد، چون حساب GitHub شما به Claude وصل نیست. دو راه ساده:

## راه ۱ (پیشنهادی): وصل کردن حساب به Claude

در Claude: **Settings ‹ Connectors ‹ GitHub ‹ Connect**. بعد در یک پیام بنویسید «مخزن را بساز»؛ بقیه‌اش را خودم انجام می‌دهم.

## راه ۲: دستی

1. در github.com وارد شوید ← **New repository** ← نام: `PromptVault` ← **Private** یا **Public** ← **Create**.
2. در صفحه‌ی مخزن: **uploading an existing file** ← همه‌ی فایل‌ها و پوشه‌های داخل ZIP پروژه (شامل پوشه‌ی `.github`) را بکشید و رها کنید ← **Commit changes**.
   - اگر پوشه‌ی `.github` مخفی بود، در ویندوز «Show hidden files» را روشن کنید.
3. تب **Actions** ← «Windows Build» ← **Run workflow**. حدود ۵ تا ۱۰ دقیقه صبر کنید.
4. بعد از پایان، پایین صفحه‌ی اجرا در **Artifacts** فایل‌های نصب را دانلود کنید.

بعد از ساخت مخزن، در برنامه ‹ تنظیمات، آدرس `https://github.com/نام-کاربری-شما/PromptVault/releases` را بگذارید.
