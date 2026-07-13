# AvertAI — Building the Android APK

This folder wraps the mobile PWA (located in `../frontend/mobile`) with [Capacitor](https://capacitorjs.com), which packages the web app into a real native Android shell — a standard `.apk` you can install directly on any Android device without needing the Play Store.

## Prerequisites

To build the APK on your machine, you need:
- [Node.js](https://nodejs.org) 18+
- [Android Studio](https://developer.android.com/studio) or a standalone Android SDK and Java JDK 17 installed.

## Build Instructions (Powershell)

Follow these terminal commands sequentially to generate the APK:

```powershell
# 1. Enter the mobile project directory
cd mobile-apk-project

# 2. Install Capacitor and Node dependencies
npm install

# 3. Create the native Android Studio project folder
npx cap add android

# 4. Copy the web app (from frontend/mobile) into the native Android project
npx cap sync

# 5. Set your Java Environment Variable to your JDK 17 (Update this path to match your machine!)
$env:JAVA_HOME = "C:\Program Files\Java\jdk-17.0.19+10\jdk-17.0.19+10"

# 6. Build the APK using Gradle
cd android
.\gradlew.bat assembleDebug
```

Once the build finishes successfully, your APK will land at:
```text
mobile-apk-project\android\app\build\outputs\apk\debug\app-debug.apk
```

Copy that file to an Android phone (via USB, email, or Google Drive) and tap it to install. 

## Connecting to the Live Backend

Right now the mobile app is pointed at your local testing API. When you deploy the real FastAPI backend to the cloud (e.g., Render, Google Cloud, or DigitalOcean), you must point the mobile app to the real URL.

Before running `npx cap sync`, edit `frontend/mobile/index.html` and add this before the main `<script>` tag:

```html
<script>window.AVERTAI_API_BASE = 'https://your-production-url.com/api/v1';</script>
```

Then re-run `npx cap sync` and `.\gradlew.bat assembleDebug` to rebuild the APK with the live URL!

## Re-syncing after future UI changes

Any time you edit the HTML, CSS, or JS in `frontend/mobile/`, you must re-run `npx cap sync` before rebuilding. Capacitor does not watch the folder live; it copies the web assets into the native project during the sync step.
