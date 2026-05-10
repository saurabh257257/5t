# Build APK Instructions

## Quick Build (Recommended)

### Option 1: Use Android Studio (Easiest)

1. **Download Android Studio**
   - Download from: https://developer.android.com/studio
   - Install on your Windows machine

2. **Open Project**
   - Open Android Studio
   - Select: `File → Open`
   - Navigate to: `5t/android-app`
   - Click `OK`
   - Wait for Gradle sync (automatic)

3. **Build APK**
   - Menu: `Build → Build Bundle(s) / APK(s) → Build APK(s)`
   - Wait for build to complete
   - A dialog will show APK location

4. **Find APK**
   - Path: `5t/android-app/app/build/outputs/apk/debug/app-debug.apk`

---

## Advanced Build (Command Line)

### Prerequisites
- Java 11 or higher
- Android SDK installed
- Gradle 8.0 or higher

### Step 1: Set Up Environment

**Windows CMD:**
```cmd
set ANDROID_HOME=C:\Users\YourUsername\AppData\Local\Android\Sdk
set PATH=%PATH%;%ANDROID_HOME%\tools\bin
```

**Windows PowerShell:**
```powershell
$env:ANDROID_HOME = "C:\Users\YourUsername\AppData\Local\Android\Sdk"
$env:PATH = $env:PATH + ";$env:ANDROID_HOME\tools\bin"
```

### Step 2: Verify Setup

```bash
java -version
# Should show Java 11 or higher

sdkmanager --version
# Should show SDK version
```

### Step 3: Build APK

```bash
cd 5t/android-app

# Option A: Using Gradle (if installed globally)
gradle assembleDebug

# Option B: Using Gradle Wrapper (download if needed)
./gradlew assembleDebug

# Option C: Using the build script (Linux/Mac)
bash buildApk.sh
```

### Step 4: Locate APK

After build completes, find APK at:
```
5t/android-app/app/build/outputs/apk/debug/app-debug.apk
```

---

## Install APK on Device

### Method 1: Using ADB (Recommended)

```bash
# Connect device via USB (enable Developer Mode first)
adb install 5t/android-app/app/build/outputs/apk/debug/app-debug.apk
```

### Method 2: Manual Installation

1. Copy `app-debug.apk` to your phone (via USB or cloud)
2. Open file manager on phone
3. Tap the APK file
4. Tap `Install` (may need to enable "Unknown Sources")
5. App launches when installation completes

### Method 3: Via Android Studio

1. Connect phone via USB
2. Android Studio → `Run → Run 'app'`
3. Select device from list
4. App installs and launches

---

## Troubleshooting

### "gradle: command not found"
- Download Gradle: https://gradle.org/releases/
- Add to PATH or use `./gradlew` instead

### "Android SDK not found"
- Download Android Studio (includes SDK)
- Or download SDK directly: https://developer.android.com/studio/command-line

### Build fails with version error
- Update Android SDK Build Tools:
  ```bash
  sdkmanager "build-tools;34.0.0"
  sdkmanager "platforms;android-34"
  ```

### "Permission denied" on gradlew
```bash
# Linux/Mac only
chmod +x gradlew
```

### App crashes after install
- Check server URL in `MainActivity.java` line 17
- Verify server is running: `http://143.244.140.57:3000`
- Check device has internet permission

---

## Build Configuration

### Server URL
Edit `MainActivity.java` (line 17):
```java
private String serverUrl = "http://143.244.140.57:3000";
```

Change `143.244.140.57` to your server IP if different.

### App Version
Edit `app/build.gradle.kts`:
```kotlin
android {
    defaultConfig {
        versionCode = 1      // Increment for updates
        versionName = "1.0"  // Version string
    }
}
```

---

## Release Build (For App Store)

```bash
# Create release APK (optimized, smaller size)
./gradlew assembleRelease

# Output: app/build/outputs/apk/release/app-release.apk
```

**Note:** Release builds require signing keys. Setup in Android Studio:
- Menu: `Build → Generate Signed Bundle / APK`

---

## Pre-built APK

If you encounter build issues, pre-built APKs are available at:
```
https://github.com/saurabh257257/5t/releases
```

Or request from the project maintainer.

---

## Next Steps After Build

1. ✅ Build APK
2. ✅ Install on Android device
3. ✅ Open app
4. ✅ App connects to server at `http://143.244.140.57:3000`
5. ✅ Tap "Refresh Status" to load trading data
6. ✅ Configure support/resistance levels
7. ✅ Start trading!

---

For issues, check:
- GitHub: https://github.com/saurabh257257/5t/issues
- Server logs: `ssh root@143.244.140.57 && pm2 logs`
- Logcat: `adb logcat`

**Happy Trading! 🚀**
