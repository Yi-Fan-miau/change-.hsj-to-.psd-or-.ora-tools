import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import java.io.File

plugins {
    id("org.jetbrains.kotlin.jvm")
}

// Kotlin/JUnit class loading is unreliable when the build output lives under a
// non-ASCII Windows path. Use an ASCII build directory in that case.
if (rootProject.projectDir.absolutePath.any { it.code > 127 }) {
    layout.buildDirectory.set(
        File(System.getProperty("java.io.tmpdir"), "hsj-core-build")
    )
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    implementation("at.yawk.lz4:lz4-java:1.8.1")
    implementation("ar.com.hjg:pngj:2.1.0")

    testImplementation(kotlin("test"))
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
    testImplementation("com.github.luben:zstd-jni:1.5.7-12")
    testImplementation("org.json:json:20240303")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    val samples = providers.gradleProperty("hsj.samplesDir")
        .getOrElse(rootProject.projectDir.parentFile.resolve("samples").absolutePath)
    systemProperty("hsj.samplesDir", samples)
    systemProperty("hsj.referenceDir", rootProject.layout.buildDirectory.dir("reference").get().asFile.absolutePath)
    maxHeapSize = "2g"
}
