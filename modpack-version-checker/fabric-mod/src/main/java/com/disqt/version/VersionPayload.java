package com.disqt.version;

import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.Identifier;

import java.nio.charset.StandardCharsets;

public record VersionPayload(String version) implements CustomPacketPayload {
    public static final Type<VersionPayload> ID =
        new Type<>(Identifier.fromNamespaceAndPath("disqt", "version"));

    public static final StreamCodec<RegistryFriendlyByteBuf, VersionPayload> CODEC =
        new StreamCodec<>() {
            @Override
            public VersionPayload decode(RegistryFriendlyByteBuf buf) {
                byte[] bytes = new byte[buf.readableBytes()];
                buf.readBytes(bytes);
                return new VersionPayload(new String(bytes, StandardCharsets.UTF_8));
            }

            @Override
            public void encode(RegistryFriendlyByteBuf buf, VersionPayload payload) {
                buf.writeBytes(payload.version().getBytes(StandardCharsets.UTF_8));
            }
        };

    @Override
    public Type<? extends CustomPacketPayload> type() {
        return ID;
    }
}
