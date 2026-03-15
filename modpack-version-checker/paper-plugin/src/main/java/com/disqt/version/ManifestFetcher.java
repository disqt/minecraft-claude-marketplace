package com.disqt.version;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.bukkit.Bukkit;
import org.bukkit.plugin.Plugin;
import org.bukkit.scheduler.BukkitTask;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.logging.Level;

public class ManifestFetcher {
    private final Plugin plugin;
    private final String manifestUrl;
    private final int refreshMinutes;
    private final HttpClient httpClient;

    private volatile Snapshot snapshot = Snapshot.EMPTY;
    private BukkitTask refreshTask;

    record VersionEntry(String version, List<String> changelog) {}

    record Snapshot(String latestVersion, List<VersionEntry> versions) {
        static final Snapshot EMPTY = new Snapshot(null, Collections.emptyList());
    }

    public ManifestFetcher(Plugin plugin, String manifestUrl, int refreshMinutes) {
        this.plugin = plugin;
        this.manifestUrl = manifestUrl;
        this.refreshMinutes = refreshMinutes;
        this.httpClient = HttpClient.newHttpClient();
    }

    public void start() {
        Bukkit.getScheduler().runTaskAsynchronously(plugin, this::fetch);
        long ticks = refreshMinutes * 60L * 20L;
        refreshTask = Bukkit.getScheduler().runTaskTimerAsynchronously(
            plugin, this::fetch, ticks, ticks
        );
    }

    public void stop() {
        if (refreshTask != null) refreshTask.cancel();
    }

    private void fetch() {
        try {
            HttpRequest request = HttpRequest.newBuilder()
                .uri(new URI(manifestUrl))
                .timeout(Duration.ofSeconds(10))
                .header("User-Agent", "DisqtVersion/1.0")
                .GET()
                .build();

            HttpResponse<String> response = httpClient.send(
                request, HttpResponse.BodyHandlers.ofString()
            );

            if (response.statusCode() != 200) {
                plugin.getLogger().warning("Manifest fetch failed: HTTP " + response.statusCode());
                return;
            }

            JsonObject json = JsonParser.parseString(response.body()).getAsJsonObject();
            List<VersionEntry> versions = parseVersions(json.getAsJsonArray("versions"));
            String latestVersion = extractVersion(
                json.getAsJsonObject("latest").get("version").getAsString()
            );
            snapshot = new Snapshot(latestVersion, versions);

            plugin.getLogger().info("Manifest loaded: latest version " + latestVersion);
        } catch (Exception e) {
            plugin.getLogger().log(Level.WARNING, "Failed to fetch manifest", e);
        }
    }

    static String extractVersion(String fullVersion) {
        int lastV = fullVersion.lastIndexOf('v');
        if (lastV >= 0 && lastV < fullVersion.length() - 1) {
            return fullVersion.substring(lastV + 1).trim();
        }
        return fullVersion.trim();
    }

    static List<VersionEntry> parseVersions(JsonArray versions) {
        if (versions == null) return Collections.emptyList();
        List<VersionEntry> result = new ArrayList<>();
        for (int i = 0; i < versions.size(); i++) {
            JsonObject v = versions.get(i).getAsJsonObject();
            String version = extractVersion(v.get("version").getAsString());
            List<String> changelog = List.of();
            if (v.has("changelog") && v.get("changelog").isJsonArray()) {
                JsonArray arr = v.getAsJsonArray("changelog");
                List<String> lines = new ArrayList<>(arr.size());
                for (int j = 0; j < arr.size(); j++) {
                    lines.add(arr.get(j).getAsString());
                }
                changelog = List.copyOf(lines);
            }
            result.add(new VersionEntry(version, changelog));
        }
        return Collections.unmodifiableList(result);
    }

    static boolean isOlderVersion(String client, String latest) {
        try {
            String[] clientParts = client.split("\\.");
            String[] latestParts = latest.split("\\.");
            int len = Math.max(clientParts.length, latestParts.length);
            for (int i = 0; i < len; i++) {
                int c = i < clientParts.length ? Integer.parseInt(clientParts[i]) : 0;
                int l = i < latestParts.length ? Integer.parseInt(latestParts[i]) : 0;
                if (c < l) return true;
                if (c > l) return false;
            }
            return false;
        } catch (NumberFormatException e) {
            return !client.equals(latest);
        }
    }

    /**
     * Round-robin changelog across all versions newer than clientVersion.
     * Each version's changelog is ordered by importance, so round-robin
     * picks the most important entry from each missed version first.
     */
    static List<String> changelogSince(List<VersionEntry> allVersions,
                                       String clientVersion, int maxLines) {
        List<List<String>> changelogs = new ArrayList<>();
        for (VersionEntry entry : allVersions) {
            if (isOlderVersion(clientVersion, entry.version()) && !entry.changelog().isEmpty()) {
                changelogs.add(entry.changelog());
            }
        }

        List<String> result = new ArrayList<>();
        int round = 0;
        while (result.size() < maxLines) {
            boolean added = false;
            for (List<String> cl : changelogs) {
                if (round < cl.size()) {
                    result.add(cl.get(round));
                    added = true;
                    if (result.size() >= maxLines) break;
                }
            }
            if (!added) break;
            round++;
        }
        return result;
    }

    public List<String> getChangelogSince(String clientVersion, int maxLines) {
        return changelogSince(snapshot.versions(), clientVersion, maxLines);
    }

    public String getLatestVersion() {
        return snapshot.latestVersion();
    }
}
