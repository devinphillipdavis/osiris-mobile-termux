// JVM-only check of the Android app's platform-free Kotlin (ime, security, evidence,
// substrate, bridge, ipc, task). Compiles those sources and runs their JUnit tests without an Android SDK,
// so CI can hold them to a test rather than to a description. Android-SDK-dependent code
// (bluetooth/, contact/, notification/, share/, tile/, voice/, and Android UI/Service classes) is excluded.
plugins {
    kotlin("jvm") version "2.0.21"
}

repositories {
    mavenCentral()
}

val appSrc = layout.projectDirectory.dir("../app/src")

sourceSets {
    main {
        kotlin {
            srcDir(appSrc.dir("main/kotlin"))
            exclude(
                "**/bluetooth/**",
                "**/contact/**",
                "**/notification/**",
                "**/share/**",
                "**/tile/**",
                "**/voice/**",
                "**/ime/OsirisIME.kt",
                "**/ime/OsirisKeyboardView.kt",
                "**/task/OsirisSessionCoordinator.kt"
            )
        }
    }
    test {
        kotlin {
            srcDir(appSrc.dir("test/kotlin"))
        }
    }
}

dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.1")
    implementation("org.json:json:20231013")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

tasks.test {
    testLogging {
        events("passed", "failed", "skipped")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
}
