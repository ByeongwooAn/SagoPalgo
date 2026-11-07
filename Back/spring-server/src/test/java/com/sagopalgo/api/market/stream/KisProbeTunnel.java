package com.sagopalgo.api.market.stream;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

/** A disposable loopback TCP relay. Only the first two clients can dial upstream. */
final class KisProbeTunnel implements AutoCloseable {
    static final int CONNECTION_LIMIT = 2;
    private final URI upstream;
    private final ServerSocket listener = new ServerSocket();
    private final List<Link> links = new ArrayList<>();
    private final AtomicInteger dialed = new AtomicInteger();
    private final AtomicInteger arrivals = new AtomicInteger();
    private final ExecutorService threads = Executors.newFixedThreadPool(5, task -> {
        var thread = new Thread(task, "kis-probe-tunnel");
        thread.setDaemon(true);
        return thread;
    });
    private boolean closed;
    private boolean reset;

    KisProbeTunnel(URI upstream) throws IOException {
        if (!"ws".equals(upstream.getScheme()) || upstream.getHost() == null || upstream.getPort() <= 0
            || upstream.getUserInfo() != null || upstream.getRawQuery() != null || upstream.getFragment() != null) {
            throw new IllegalArgumentException("PROBE_UPSTREAM_INVALID");
        }
        this.upstream = upstream;
        listener.bind(new InetSocketAddress("127.0.0.1", 0));
        threads.execute(this::accept);
    }

    URI endpoint() {
        return URI.create("ws://127.0.0.1:" + listener.getLocalPort() + upstream.getRawPath());
    }

    int arrivals() { return arrivals.get(); }
    int upstreamDials() { return dialed.get(); }

    synchronized void resetFirst() throws IOException {
        if (closed || reset || arrivals.get() != 1 || links.size() != 1 || !links.get(0).forwarding
            || links.get(0).downstream.isClosed() || links.get(0).upstreamSocket.isClosed()) {
            throw new IllegalStateException("PROBE_FIRST_SOCKET_NOT_READY");
        }
        var link = links.get(0);
        link.downstream.setSoLinger(true, 0);
        link.upstreamSocket.setSoLinger(true, 0);
        reset = true;
        link.close();
    }

    private void accept() {
        try {
            while (true) {
                Socket client = listener.accept();
                synchronized (this) {
                    int attempt = arrivals.incrementAndGet();
                    if (closed || attempt > CONNECTION_LIMIT) {
                        closeSocket(client);
                        continue;
                    }
                    var link = new Link(client);
                    links.add(link);
                    threads.execute(() -> bridge(link));
                }
            }
        } catch (IOException ignored) {
            close();
        }
    }

    private void bridge(Link link) {
        try {
            link.downstream.setSoTimeout(5_000);
            var clientInput = new BufferedInputStream(link.downstream.getInputStream());
            byte[] handshake = relayHandshake(clientInput, upstream);
            synchronized (this) {
                if (closed || link.upstreamSocket.isClosed()) return;
                dialed.incrementAndGet();
            }
            link.upstreamSocket.connect(new InetSocketAddress(upstream.getHost(), upstream.getPort()), 5_000);
            link.upstreamSocket.setTcpNoDelay(true);
            link.downstream.setTcpNoDelay(true);
            link.downstream.setSoTimeout(0);
            var output = link.upstreamSocket.getOutputStream();
            output.write(handshake);
            output.flush();
            synchronized (this) {
                if (closed) return;
                link.forwarding = true;
                threads.execute(() -> copyBack(link));
            }
            clientInput.transferTo(output);
        } catch (IOException ignored) {
            // Closing both directions lets the real client's error handler decide whether to reconnect.
        } finally {
            link.close();
        }
    }

    private static void copyBack(Link link) {
        try {
            link.upstreamSocket.getInputStream().transferTo(link.downstream.getOutputStream());
        } catch (IOException ignored) {
        } finally {
            link.close();
        }
    }

    static byte[] relayHandshake(InputStream input, URI upstream) throws IOException {
        var header = new ByteArrayOutputStream();
        int suffix = 0;
        while (suffix != 0x0d0a0d0a) {
            int next = input.read();
            if (next < 0 || header.size() >= 8192) throw new IOException("PROBE_HANDSHAKE_INVALID");
            suffix = (suffix << 8) | next;
            header.write(next);
        }
        String[] lines = header.toString(StandardCharsets.US_ASCII).split("\r\n");
        if (!lines[0].equals("GET " + upstream.getRawPath() + " HTTP/1.1")) {
            throw new IOException("PROBE_HANDSHAKE_INVALID");
        }
        int hosts = 0;
        for (int i = 1; i < lines.length; i++) {
            if (lines[i].toLowerCase(Locale.ROOT).startsWith("host:")) {
                hosts++;
                lines[i] = "Host: " + upstream.getAuthority();
            }
        }
        if (hosts != 1) throw new IOException("PROBE_HANDSHAKE_INVALID");
        return (String.join("\r\n", lines) + "\r\n\r\n").getBytes(StandardCharsets.US_ASCII);
    }

    @Override public synchronized void close() {
        if (closed) return;
        closed = true;
        try { listener.close(); } catch (IOException ignored) {}
        links.forEach(Link::close);
        threads.shutdownNow();
    }

    private static void closeSocket(Socket socket) {
        try { socket.close(); } catch (IOException ignored) {}
    }

    private static final class Link {
        final Socket downstream;
        final Socket upstreamSocket = new Socket();
        boolean forwarding;
        Link(Socket downstream) { this.downstream = downstream; }
        void close() {
            closeSocket(downstream);
            closeSocket(upstreamSocket);
        }
    }

}
