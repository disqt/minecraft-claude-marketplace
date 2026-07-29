plugins {
    java
}

group = "com.disqt"
version = "1.0.0"

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(25))
}

repositories {
    mavenCentral()
    maven("https://repo.papermc.io/repository/maven-public/")
}

dependencies {
    compileOnly("io.papermc.paper:paper-api:26.2.build.87-stable")
    testCompileOnly("io.papermc.paper:paper-api:26.2.build.87-stable")
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
    testRuntimeOnly("com.google.code.gson:gson:2.10.1")
}

tasks.jar {
    archiveBaseName.set("DisqtVersion")
}

tasks.test {
    useJUnitPlatform()
}
