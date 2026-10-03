plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.neoscan.player"
    compileSdk = 36
    ndkVersion = "30.0.16248370"
    defaultConfig {
        applicationId = "com.neoscan.player"
        minSdk = 26
        targetSdk = 36
        versionCode = 8
        versionName = "0.0.8"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
        // where builds are published (examples/brawler make publish-vps)
        buildConfigField("String", "ROM_URL", "\"https://canneji.duckdns.org/brawler/download/\"")
    }
    externalNativeBuild { ndkBuild { path = file("src/main/cpp/Android.mk") } }
    buildTypes { release { isMinifyEnabled = false; signingConfig = signingConfigs.getByName("debug") } }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    androidResources { noCompress += listOf("zip", "neo") }
    buildFeatures { buildConfig = true }
}
