plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    // Android 네이티브 코드가 속할 기본 네임스페이스입니다.
    // Google/Naver OAuth, Android Manifest, Kotlin MainActivity와 같은 Android 계층에서 이 값을 기준으로 앱을 식별합니다.
    namespace = "com.sagopalgo.app"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // Google OAuth Android 클라이언트 ID를 만들 때 입력하는 실제 Android 패키지명입니다.
        // 한 번 배포한 뒤에는 Play Store와 OAuth 설정에 연결되므로 가볍게 바꾸지 않는 값으로 관리합니다.
        applicationId = "com.sagopalgo.app"

        // 아래 값들은 Flutter 프로젝트의 Android 빌드 기준값을 그대로 따릅니다.
        // Flutter SDK 설정을 기준으로 최소/대상 SDK와 앱 버전이 Android Gradle 빌드에 전달됩니다.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            // 아직 정식 배포 서명키를 만들기 전이므로 debug signing config를 임시로 사용합니다.
            // Play Store 배포 전에는 별도의 release keystore를 만들고 이 설정을 운영 서명 설정으로 교체해야 합니다.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
