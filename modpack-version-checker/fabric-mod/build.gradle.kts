plugins {
    id("net.fabricmc.fabric-loom") version "1.16-SNAPSHOT"
    java
}

version = project.property("mod_version")!!
group = project.property("maven_group")!!

repositories {
    mavenCentral()
}

dependencies {
    minecraft("com.mojang:minecraft:${project.property("minecraft_version")}")
    implementation("net.fabricmc:fabric-loader:${project.property("loader_version")}")
    implementation("net.fabricmc.fabric-api:fabric-api:${project.property("fabric_version")}")
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(25))
}

tasks.processResources {
    // fabric.mod.json declares "version": "${version}" -- substitute it, otherwise Fabric
    // Loader warns the version is not valid SemVer and cannot evaluate dependencies.
    inputs.property("version", project.version)
    filesMatching("fabric.mod.json") {
        expand("version" to project.version)
    }
}
