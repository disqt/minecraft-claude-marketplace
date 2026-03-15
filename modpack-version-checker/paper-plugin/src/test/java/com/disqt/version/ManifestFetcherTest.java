package com.disqt.version;

import org.junit.jupiter.api.Test;

import com.google.gson.JsonArray;
import com.google.gson.JsonParser;

import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class ManifestFetcherTest {

    @Test
    void extractVersion_fullFormat() {
        assertEquals("2.2", ManifestFetcher.extractVersion("1.21.11 v2.2"));
    }

    @Test
    void extractVersion_plainVersion() {
        assertEquals("2.2", ManifestFetcher.extractVersion("2.2"));
    }

    @Test
    void extractVersion_withWhitespace() {
        assertEquals("2.2", ManifestFetcher.extractVersion("1.21.11 v2.2 "));
    }

    @Test
    void extractVersion_majorMinorPatch() {
        assertEquals("2.2.1", ManifestFetcher.extractVersion("1.21.11 v2.2.1"));
    }

    @Test
    void isOlderVersion_basic() {
        assertTrue(ManifestFetcher.isOlderVersion("2.1", "2.5"));
        assertFalse(ManifestFetcher.isOlderVersion("2.5", "2.5"));
        assertFalse(ManifestFetcher.isOlderVersion("2.6", "2.5"));
    }

    @Test
    void isOlderVersion_differentLengths() {
        assertTrue(ManifestFetcher.isOlderVersion("2", "2.1"));
        assertFalse(ManifestFetcher.isOlderVersion("2.1", "2"));
    }

    @Test
    void parseVersions_basic() {
        String json = """
            [
              { "version": "1.21.11 v2.5", "changelog": ["New biomes", "Bug fix A"] },
              { "version": "1.21.11 v2.4", "changelog": ["PvP overhaul", "Perf boost", "Minor fix"] },
              { "version": "1.21.11 v2.3" },
              { "version": "1.21.11 v2.2", "changelog": ["Shaders fixed"] }
            ]
            """;
        JsonArray arr = JsonParser.parseString(json).getAsJsonArray();
        List<ManifestFetcher.VersionEntry> versions = ManifestFetcher.parseVersions(arr);
        assertEquals(4, versions.size());
        assertEquals("2.5", versions.get(0).version());
        assertEquals(List.of("New biomes", "Bug fix A"), versions.get(0).changelog());
        assertEquals("2.3", versions.get(2).version());
        assertTrue(versions.get(2).changelog().isEmpty());
    }

    @Test
    void parseVersions_null() {
        List<ManifestFetcher.VersionEntry> versions = ManifestFetcher.parseVersions(null);
        assertTrue(versions.isEmpty());
    }

    @Test
    void changelogSince_picksMostImportantFromEachVersion() {
        List<ManifestFetcher.VersionEntry> versions = List.of(
            new ManifestFetcher.VersionEntry("2.5", List.of("V5 top", "V5 second")),
            new ManifestFetcher.VersionEntry("2.4", List.of("V4 top", "V4 second")),
            new ManifestFetcher.VersionEntry("2.3", List.of("V3 top")),
            new ManifestFetcher.VersionEntry("2.2", List.of("V2 top", "V2 second")),
            new ManifestFetcher.VersionEntry("2.1", List.of("V1 top"))
        );
        List<String> result = ManifestFetcher.changelogSince(versions, "2.1", 3);
        assertEquals(List.of("V5 top", "V4 top", "V3 top"), result);
    }

    @Test
    void changelogSince_wrapsToSecondRound() {
        List<ManifestFetcher.VersionEntry> versions = List.of(
            new ManifestFetcher.VersionEntry("2.4", List.of("V4 top", "V4 second")),
            new ManifestFetcher.VersionEntry("2.3", List.of("V3 top", "V3 second")),
            new ManifestFetcher.VersionEntry("2.2", List.of("V2 top"))
        );
        List<String> result = ManifestFetcher.changelogSince(versions, "2.1", 5);
        assertEquals(List.of("V4 top", "V3 top", "V2 top", "V4 second", "V3 second"), result);
    }

    @Test
    void changelogSince_skipsClientVersionAndOlder() {
        List<ManifestFetcher.VersionEntry> versions = List.of(
            new ManifestFetcher.VersionEntry("2.5", List.of("V5 change")),
            new ManifestFetcher.VersionEntry("2.4", List.of("V4 change")),
            new ManifestFetcher.VersionEntry("2.3", List.of("V3 change"))
        );
        List<String> result = ManifestFetcher.changelogSince(versions, "2.4", 3);
        assertEquals(List.of("V5 change"), result);
    }
}
