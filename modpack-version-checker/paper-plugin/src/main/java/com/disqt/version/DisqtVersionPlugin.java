package com.disqt.version;

import org.bukkit.plugin.java.JavaPlugin;

public class DisqtVersionPlugin extends JavaPlugin {
    private ManifestFetcher manifestFetcher;

    @Override
    public void onEnable() {
        saveDefaultConfig();

        String manifestUrl = getConfig().getString("manifest-url");
        int refreshMinutes = getConfig().getInt("refresh-minutes", 30);

        manifestFetcher = new ManifestFetcher(this, manifestUrl, refreshMinutes);
        manifestFetcher.start();

        VersionListener listener = new VersionListener(this, manifestFetcher);
        getServer().getMessenger().registerIncomingPluginChannel(this, "disqt:version", listener);
        getServer().getPluginManager().registerEvents(listener, this);

        getLogger().info("DisqtVersion enabled — listening on disqt:version");
    }

    @Override
    public void onDisable() {
        if (manifestFetcher != null) manifestFetcher.stop();
        getServer().getMessenger().unregisterIncomingPluginChannel(this);
    }
}
