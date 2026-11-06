package com.sagopalgo.api.market.stream;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Real RFC6455 loopback transport with synthetic frames, never a KIS/provider server. */
final class LoopbackWebSocketServer implements AutoCloseable {
    record Frame(int opcode,byte[] bytes) {String text() {return new String(bytes,StandardCharsets.UTF_8);}}
    private final ServerSocket server;
    private final ExecutorService tasks=Executors.newCachedThreadPool(task->{var thread=new Thread(task,"loopback-websocket");thread.setDaemon(true);return thread;});
    private final BlockingQueue<Peer> arrivals=new LinkedBlockingQueue<>();
    private final List<Peer> peers=new CopyOnWriteArrayList<>();
    private final AtomicInteger accepted=new AtomicInteger();
    private final CountDownLatch handshakeSeen=new CountDownLatch(1),handshakeRelease;
    private volatile boolean stopped;
    LoopbackWebSocketServer() throws IOException {this(false);}
    LoopbackWebSocketServer(boolean holdHandshake) throws IOException {
        handshakeRelease=new CountDownLatch(holdHandshake?1:0);
        server=new ServerSocket();server.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"),0));
        server.setSoTimeout(200);
        tasks.submit(()->{
            while(!stopped) {
                try {
                    var socket=server.accept();socket.setSoTimeout(2000);
                    var peer=new Peer(socket);peers.add(peer);
                    tasks.submit(()->{
                        try {peer.handshake(handshakeSeen,handshakeRelease);accepted.incrementAndGet();arrivals.add(peer);peer.read();}
                        catch(Exception ignored) {peer.close();}
                    });
                } catch(SocketTimeoutException ignored) {} catch(IOException error) {if(!stopped)throw new UncheckedIOException(error);}
            }
        });
    }
    URI endpoint() {return URI.create("ws://127.0.0.1:"+server.getLocalPort()+"/synthetic-public");}
    Peer next() throws InterruptedException {
        var peer=arrivals.poll(5,TimeUnit.SECONDS);
        if(peer==null)throw new AssertionError("LOOPBACK_CONNECTION_TIMEOUT");return peer;
    }
    boolean noNext(long milliseconds) throws InterruptedException {return arrivals.poll(milliseconds,TimeUnit.MILLISECONDS)==null;}
    int accepted() {return accepted.get();}
    boolean handshakePending() throws InterruptedException {return handshakeSeen.await(3,TimeUnit.SECONDS);}
    void releaseHandshake() {handshakeRelease.countDown();}
    @Override public void close() throws IOException {
        stopped=true;releaseHandshake();server.close();peers.forEach(Peer::close);tasks.shutdownNow();
    }
    static final class Peer {
        final Socket socket;
        final InputStream input;
        final OutputStream output;
        final BlockingQueue<Frame> frames=new LinkedBlockingQueue<>();
        Peer(Socket socket) throws IOException {this.socket=socket;input=socket.getInputStream();output=socket.getOutputStream();}
        void handshake(CountDownLatch seen,CountDownLatch release) throws Exception {
            var header=new ByteArrayOutputStream();int state=0;
            while(state!=4) {
                int value=input.read();if(value<0 || header.size()>8192)throw new IOException("HANDSHAKE_INVALID");
                header.write(value);
                state=switch(state) {case 0->value=='\r'?1:0;case 1->value=='\n'?2:0;case 2->value=='\r'?3:0;default->value=='\n'?4:0;};
            }
            String key=Arrays.stream(header.toString(StandardCharsets.US_ASCII).split("\r\n"))
                .filter(line->line.toLowerCase(Locale.ROOT).startsWith("sec-websocket-key:"))
                .map(line->line.substring(line.indexOf(':')+1).trim()).findFirst().orElseThrow();
            String accept=Base64.getEncoder().encodeToString(MessageDigest.getInstance("SHA-1")
                .digest((key+"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").getBytes(StandardCharsets.US_ASCII)));
            seen.countDown();if(!release.await(5,TimeUnit.SECONDS))throw new IOException("TEST_HANDSHAKE_RELEASE_TIMEOUT");
            output.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: "+accept+"\r\n\r\n").getBytes(StandardCharsets.US_ASCII));output.flush();
            socket.setSoTimeout(0);
        }
        void read() throws IOException {
            for(;;) {
                int first=input.read();if(first<0)return;int second=input.read();if(second<0)throw new EOFException();
                long length=second&127;
                if(length==126)length=((long)required()<<8)|required();
                else if(length==127) {length=0;for(int i=0;i<8;i++)length=(length<<8)|required();}
                if((second&128)==0 || length<0 || length>262144)throw new IOException("CLIENT_FRAME_INVALID");
                byte[] mask=readBytes(4),bytes=readBytes((int)length);
                for(int i=0;i<bytes.length;i++)bytes[i]^=mask[i%4];
                frames.add(new Frame(first&15,bytes));
                if((first&15)==8)return;
            }
        }
        int required() throws IOException {int value=input.read();if(value<0)throw new EOFException();return value;}
        byte[] readBytes(int length) throws IOException {byte[] value=input.readNBytes(length);if(value.length!=length)throw new EOFException();return value;}
        Frame frame(int opcode) throws InterruptedException {
            long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(5);
            while(System.nanoTime()<deadline) {
                var value=frames.poll(100,TimeUnit.MILLISECONDS);if(value!=null && value.opcode()==opcode)return value;
            }
            throw new AssertionError("LOOPBACK_FRAME_TIMEOUT_"+opcode);
        }
        synchronized void send(int opcode,boolean last,byte[] bytes) throws IOException {
            output.write((last?128:0)|opcode);
            if(bytes.length<126)output.write(bytes.length);
            else if(bytes.length<=65535) {output.write(126);output.write(bytes.length>>8);output.write(bytes.length&255);}
            else {output.write(127);for(int shift=56;shift>=0;shift-=8)output.write((int)((long)bytes.length>>shift)&255);}
            output.write(bytes);output.flush();
        }
        void text(String text) throws IOException {send(1,true,text.getBytes(StandardCharsets.UTF_8));}
        void fragmented(String text) throws IOException {
            byte[] bytes=text.getBytes(StandardCharsets.UTF_8);int half=bytes.length/2;
            send(1,false,Arrays.copyOfRange(bytes,0,half));send(0,true,Arrays.copyOfRange(bytes,half,bytes.length));
        }
        void ping() throws IOException {send(9,true,new byte[]{1,2,3});}
        void normalClose() throws IOException {send(8,true,new byte[]{3,(byte)232});}
        void reset() throws IOException {socket.setSoLinger(true,0);socket.close();}
        void close() {try {socket.close();} catch(IOException ignored) {}}
    }
}
