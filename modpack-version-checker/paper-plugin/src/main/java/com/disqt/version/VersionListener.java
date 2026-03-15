package com.disqt.version;

import net.kyori.adventure.text.minimessage.MiniMessage;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.plugin.Plugin;
import org.bukkit.plugin.messaging.PluginMessageListener;
import org.bukkit.scheduler.BukkitTask;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public class VersionListener implements Listener, PluginMessageListener {
    private final Plugin plugin;
    private final ManifestFetcher fetcher;
    private final MiniMessage miniMessage = MiniMessage.miniMessage();
    private final Map<UUID, BukkitTask> pendingChecks = new ConcurrentHashMap<>();

    private final String outdatedTemplate;
    private final String changelogLineTemplate;
    private final String noModpackTemplate;
    private final int changelogLines;

    public VersionListener(Plugin plugin, ManifestFetcher fetcher) {
        this.plugin = plugin;
        this.fetcher = fetcher;
        this.outdatedTemplate = plugin.getConfig().getString("messages.outdated");
        this.changelogLineTemplate = plugin.getConfig().getString("messages.changelog-line");
        this.noModpackTemplate = plugin.getConfig().getString("messages.no-modpack");
        this.changelogLines = plugin.getConfig().getInt("changelog-lines", 3);
    }

    @EventHandler
    public void onPlayerJoin(PlayerJoinEvent event) {
        Player player = event.getPlayer();
        BukkitTask task = Bukkit.getScheduler().runTaskLater(plugin, () -> {
            pendingChecks.remove(player.getUniqueId());
            if (player.isOnline()) {
                player.sendMessage(miniMessage.deserialize(noModpackTemplate));
            }
        }, 100L);
        pendingChecks.put(player.getUniqueId(), task);
    }

    @Override
    public void onPluginMessageReceived(String channel, Player player, byte[] message) {
        if (!channel.equals("disqt:version")) return;

        BukkitTask task = pendingChecks.remove(player.getUniqueId());
        if (task != null) task.cancel();

        String clientVersion = new String(message, StandardCharsets.UTF_8).trim();
        String latestVersion = fetcher.getLatestVersion();

        if (latestVersion == null) return;

        if (ManifestFetcher.isOlderVersion(clientVersion, latestVersion)) {
            String msg = outdatedTemplate.replace("{latest}", latestVersion);
            player.sendMessage(miniMessage.deserialize(msg));

            List<String> changelog = fetcher.getChangelogSince(clientVersion, changelogLines);
            for (String entry : changelog) {
                String line = changelogLineTemplate.replace("{line}", entry);
                player.sendMessage(miniMessage.deserialize(line));
            }
        }
    }
}
