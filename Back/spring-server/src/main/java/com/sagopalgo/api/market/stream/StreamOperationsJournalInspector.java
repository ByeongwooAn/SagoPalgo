package com.sagopalgo.api.market.stream;

import com.sagopalgo.api.common.util.ContentHash;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;

/** Bounded read-only verification. Never repairs/truncates an old run or resumes its connection. */
public final class StreamOperationsJournalInspector {
    static Map<String,Object> inspect(Path directory,UUID selected,long after,int limit) throws IOException {
        if(after<0 || limit<1 || limit>1000 || Files.isSymbolicLink(directory) || !Files.isDirectory(directory))
            throw new IllegalArgumentException("JOURNAL_INSPECTION_INPUT_INVALID");
        var files=new ArrayList<Path>();long total=0;
        try(var stream=Files.newDirectoryStream(directory,"session-*.jsonl")) {
            for(var path:stream) {
                if(files.size()>=StreamOperationsJournal.MAX_FILES || Files.isSymbolicLink(path) || !Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS))
                    throw new IllegalArgumentException("JOURNAL_INSPECTION_LIMIT");
                total=Math.addExact(total,Files.size(path));
                if(total>StreamOperationsJournal.READ_DIRECTORY_LIMIT)throw new IllegalArgumentException("JOURNAL_INSPECTION_LIMIT");
                files.add(path);
            }
        }
        files.sort(Comparator.comparing(path->path.getFileName().toString()));
        var sessions=new ArrayList<Map<String,Object>>();
        for(Path path:files) {
            String name=path.getFileName().toString();
            UUID id=UUID.fromString(name.substring(8,name.length()-6));
            if(!name.equals("session-"+id+".jsonl"))throw new IllegalArgumentException("JOURNAL_FILENAME_INVALID");
            if(selected==null || id.equals(selected))sessions.add(scan(path,id,selected!=null,after,limit));
        }
        if(selected!=null && sessions.isEmpty())throw new IllegalArgumentException("JOURNAL_SESSION_MISSING");
        return Map.of("schemaVersion","SAGOPALGO_STREAM_OPERATIONS_INSPECTION_V1","sessions",sessions,
            "crossSessionOrder","UNCONFIRMED","writerActivity","NOT_DETERMINED","repairPerformed",false,
            "durabilityAttestedByReader",false,"usableForTrading",false);
    }
    private static Map<String,Object> scan(Path path,UUID session,boolean include,long after,int limit) throws IOException {
        byte[] raw;
        try(var input=Files.newInputStream(path,LinkOption.NOFOLLOW_LINKS)) {
            raw=input.readNBytes((int)StreamOperationsJournal.READ_FILE_LIMIT+1);
        }
        if(raw.length>StreamOperationsJournal.READ_FILE_LIMIT)throw new IllegalArgumentException("JOURNAL_INSPECTION_LIMIT");
        long index=0,sourceSequence=0,elapsed=0,generation=0;UUID domain=null;
        String previous=StreamOperationsJournal.ZERO,status="NO_END_MARKER";
        StreamOperationsJournal.Operation last=null;
        var counters=StreamOperationsJournal.Counters.zero();
        var page=new ArrayList<StreamOperationsJournal.Entry>();
        boolean ended=false;int begin=0;
        for(int i=0;i<raw.length;i++) {
            if(raw[i]!='\n')continue;
            try {
                if(i-begin<=0 || i-begin>StreamOperationsJournal.MAX_LINE || index>=100000)throw new IllegalArgumentException();
                var record=StreamOperationsJournal.JSON.readValue(Arrays.copyOfRange(raw,begin,i),StreamOperationsJournal.Entry.class);
                var body=record.entry();var operation=body.operation();
                if(ended || body.kind()==null || !body.schemaVersion().equals(StreamOperationsJournal.VERSION) || body.utcSynchronized() ||
                    !session.equals(body.sessionId()) || body.clockDomain()==null || body.index()!=index+1 ||
                    !previous.equals(body.previousHash()) || !ContentHash.sha256(StreamOperationsJournal.JSON.writeValueAsString(body)).equals(record.hash()) ||
                    operation.elapsedNanos()<elapsed || operation.generation()<generation || !operation.counters().follows(counters) ||
                    body.kind()!=StreamOperationsJournal.Kind.LIFECYCLE && operation.code()!=null)throw new IllegalArgumentException();
                if(index==0) {
                    if(body.kind()!=StreamOperationsJournal.Kind.START || operation.sourceSequence()!=0 || !operation.state().equals("SESSION_START"))throw new IllegalArgumentException();
                    domain=body.clockDomain();
                } else {
                    if(!domain.equals(body.clockDomain()) || body.kind()==StreamOperationsJournal.Kind.START)throw new IllegalArgumentException();
                    if(body.kind()==StreamOperationsJournal.Kind.LIFECYCLE) {
                        if(Set.of("SESSION_START","SESSION_END","COUNTERS").contains(operation.state()) || operation.sourceSequence()!=sourceSequence+1)throw new IllegalArgumentException();
                    } else if(operation.sourceSequence()!=sourceSequence ||
                        body.kind()==StreamOperationsJournal.Kind.COUNTERS && !operation.state().equals("COUNTERS") ||
                        body.kind()==StreamOperationsJournal.Kind.END && !operation.state().equals("SESSION_END"))throw new IllegalArgumentException();
                }
                index=body.index();sourceSequence=operation.sourceSequence();elapsed=operation.elapsedNanos();generation=operation.generation();
                counters=operation.counters();last=operation;previous=record.hash();ended=body.kind()==StreamOperationsJournal.Kind.END;
                if(include && index>after && page.size()<limit)page.add(record);
            } catch(Exception error) {status="CORRUPT";begin=i+1;break;}
            begin=i+1;
        }
        if(!status.equals("CORRUPT"))status=begin<raw.length?"PARTIAL_TAIL":ended?"CLEAN_END":"NO_END_MARKER";
        if(raw.length==0)status="EMPTY";
        var result=new LinkedHashMap<String,Object>();
        result.put("sessionId",session);result.put("fileSha256",hash(raw));result.put("status",status);
        result.put("verifiedEntries",index);result.put("lastVerifiedHash",previous);result.put("lastOperation",last);
        result.put("clockDomain",domain);result.put("utcSynchronized",false);result.put("entries",page);
        result.put("nextAfterIndex",page.isEmpty()?after:page.get(page.size()-1).entry().index());
        result.put("countersAreObservationSnapshots",true);result.put("missingOperationsReconstructed",false);
        return result;
    }
    private static String hash(byte[] raw) {
        try {return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw));}
        catch(NoSuchAlgorithmException e) {throw new IllegalStateException(e);}
    }
    static int run(String[] args) {
        try {
            var values=new HashMap<String,String>();
            if(args.length%2!=0)throw new IllegalArgumentException();
            for(int i=0;i<args.length;i+=2)if(!Set.of("--directory","--output","--session","--after-index","--limit").contains(args[i]) || values.put(args[i],args[i+1])!=null)throw new IllegalArgumentException();
            var report=inspect(Path.of(values.get("--directory")),values.containsKey("--session")?UUID.fromString(values.get("--session")):null,
                Long.parseLong(values.getOrDefault("--after-index","0")),Integer.parseInt(values.getOrDefault("--limit","100")));
            try(var output=Files.newOutputStream(Path.of(values.get("--output")),StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)) {
                output.write(StreamOperationsJournal.JSON.writeValueAsBytes(report));
            }
            return 0;
        } catch(Exception e) {System.err.println("{\"status\":\"FAILED\",\"code\":\"JOURNAL_INSPECTION_FAILED\"}");return 2;}
    }
    public static void main(String[] args) {System.exit(run(args));}
}
