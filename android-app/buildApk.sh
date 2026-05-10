#!/bin/bash

# 5T Trading Bot APK Builder
# Builds debug APK using Gradle

echo "🤖 5T Trading Bot - APK Builder"
echo "================================"
echo ""

# Check if ANDROID_HOME is set
if [ -z "$ANDROID_HOME" ]; then
    echo "⚠️  ANDROID_HOME not set!"
    echo "Please set ANDROID_HOME to your Android SDK location:"
    echo "  export ANDROID_HOME=/path/to/android/sdk"
    echo ""
    exit 1
fi

echo "✅ Android SDK: $ANDROID_HOME"
echo ""

# Check if Java is installed
if ! command -v java &> /dev/null; then
    echo "❌ Java is not installed!"
    echo "Install Java 11 or higher"
    exit 1
fi

java_version=$(java -version 2>&1 | grep "version")
echo "✅ Java: $java_version"
echo ""

# Create local.properties
echo "Creating local.properties..."
cat > local.properties << EOF
sdk.dir=$ANDROID_HOME
EOF
echo "✅ local.properties created"
echo ""

# Build APK
echo "📦 Building APK..."
echo ""

if [ -f "gradlew" ]; then
    ./gradlew assembleDebug
else
    echo "⚠️  gradlew not found, attempting download..."
    # Try using gradle if installed
    gradle wrapper --gradle-version 8.0
    ./gradlew assembleDebug
fi

# Check if build succeeded
if [ -f "app/build/outputs/apk/debug/app-debug.apk" ]; then
    echo ""
    echo "✅ APK built successfully!"
    echo ""
    echo "📁 APK Location:"
    echo "   $(pwd)/app/build/outputs/apk/debug/app-debug.apk"
    echo ""
    echo "📲 To install on device:"
    echo "   adb install app/build/outputs/apk/debug/app-debug.apk"
    echo ""
else
    echo ""
    echo "❌ Build failed!"
    echo "Check the error messages above"
    exit 1
fi
