package com.sagopalgo.api.market.stream;

import static org.assertj.core.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.config.ResearchProviderProperties;
import com.sagopalgo.api.research.mapper.*;
import com.sagopalgo.api.research.model.*;
import com.sagopalgo.api.research.service.*;
import com.sagopalgo.api.research.export.StoredDatasetExportService;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.mybatis.spring.*;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;
import org.springframework.jdbc.datasource.init.ScriptUtils;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionInterceptor;
import org.springframework.transaction.support.TransactionTemplate;

@EnabledIfEnvironmentVariable(named="SAGOPALGO_MARKET_RESEARCH_MYSQL_TEST",matches="true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class MarketResearchMysqlIntegrationTest {
    DriverManagerDataSource source;
    JdbcTemplate jdbc;
    DataSourceTransactionManager manager;
    SqlSessionTemplate session;
    MarketStreamStore stream;
    ResearchJournalStore journal;
    ResearchFeedStore feed;
    ResearchJournalMapper journalMapper;
    final ObjectMapper json=new ObjectMapper().findAndRegisterModules();
    final ResearchRequest request=new ResearchRequest("005930","삼성전자",LocalDate.of(2026,10,1),LocalDate.of(2026,11,3));
    @BeforeAll void initializeOnlyMarkedDatabase() throws Exception {
        source=new DriverManagerDataSource("jdbc:mysql://127.0.0.1:33318/sagopalgo_market_research_test?allowPublicKeyRetrieval=true&useSSL=false&serverTimezone=UTC","root","market-research-test-only");
        jdbc=new JdbcTemplate(source);manager=new DataSourceTransactionManager(source);
        assertThat(jdbc.queryForObject("SELECT DATABASE()",String.class)).isEqualTo("sagopalgo_market_research_test");
        assertThat(jdbc.queryForObject("SELECT marker FROM isolated_test_environment_marker",String.class)).isEqualTo("SAGOPALGO_ISOLATED_MARKET_RESEARCH_TEST_ONLY");
        try(var connection=source.getConnection()) {
            for(String name:List.of("002_research_feed_storage.sql","025_market_stream.sql","026_research_incremental.sql"))
                ScriptUtils.executeSqlScript(connection,new FileSystemResource("../database/migrations/"+name));
            // 재적용 시 기존 이력/커서를 초기화하지 않습니다.
            ScriptUtils.executeSqlScript(connection,new FileSystemResource("../database/migrations/026_research_incremental.sql"));
        }
        var config=new Configuration();config.setMapUnderscoreToCamelCase(true);
        for(var type:List.of(MarketStreamMapper.class,ResearchJournalMapper.class,ResearchNewsMapper.class,ResearchDisclosureMapper.class)) config.addMapper(type);
        var factory=new SqlSessionFactoryBean();factory.setDataSource(source);factory.setConfiguration(config);session=new SqlSessionTemplate(factory.getObject());
    }
    @BeforeEach void resetOnlyTestFixtures() {
        for(String table:List.of("research_versions","research_item_heads","research_checkpoints","research_news","research_disclosures","market_stream_minutes","market_stream_events")) jdbc.update("DELETE FROM "+table);
        jdbc.update("UPDATE research_journal_clock SET last_id=0 WHERE singleton=1");
        var policy=new ResearchProviderProperties();policy.getIncremental().setEnabled(true);
        journalMapper=session.getMapper(ResearchJournalMapper.class);
        journal=new ResearchJournalStore(journalMapper,json,policy);
        feed=proxy(new ResearchFeedStore(session.getMapper(ResearchNewsMapper.class),session.getMapper(ResearchDisclosureMapper.class),journal));
        stream=proxy(new MarketStreamStore(session.getMapper(MarketStreamMapper.class),json));
    }
    @SuppressWarnings("unchecked") <T>T proxy(T value) {
        var factory=new ProxyFactory(value);factory.setProxyTargetClass(true);
        factory.addAdvice(new TransactionInterceptor(manager,new AnnotationTransactionAttributeSource()));return (T)factory.getProxy();
    }
    MarketStreamEvent tick(String time,String price,String volume,String cumulative) {
        return new KisStreamDecoder().decode(MarketStreamTest.trade(time,price,volume,cumulative),MarketStreamTest.NOW).get(0);
    }
    NewsArticle article(String title,String link) {return new NewsArticle("NAVER_NEWS","005930",title,"https://news.test/"+link,"요약",Instant.parse("2026-11-03T01:00:00Z"));}
    @Test void duplicateAndConflictingTradeNeverDoubleCountsVolume() {
        var event=tick("100001","100","2","2");assertThat(stream.append(event)).isTrue();assertThat(stream.append(event)).isFalse();
        assertThatThrownBy(()->stream.append(tick("100001","101","2","2"))).hasMessage("STREAM_EVENT_CONFLICT");
        var bars=stream.minutes("005930",MarketStreamTest.NOW.minusSeconds(100));
        assertThat(bars).hasSize(1);assertThat(bars.get(0).volume()).isEqualTo("2");assertThat(bars.get(0).trades()).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM market_stream_events",Integer.class)).isEqualTo(1);
    }
    @Test void lateTradesSurviveStoreRecreationWithCorrectOhlc() {
        stream.append(tick("100003","103","2","5"));stream.append(tick("100001","101","1","1"));stream.append(tick("100003","102","2","3"));
        var recreated=new MarketStreamStore(session.getMapper(MarketStreamMapper.class),json);
        var bar=recreated.minutes("005930",MarketStreamTest.NOW.minusSeconds(100)).get(0);
        assertThat(bar.open()).isEqualTo("101");assertThat(bar.close()).isEqualTo("103");assertThat(bar.volume()).isEqualTo("5");
    }
    @Test void barFailureRollsBackEventReceiptAndCanBeRetriedExactlyOnce() {
        stream.append(tick("100001","100","1","1"));
        jdbc.execute("CREATE TRIGGER test_minute_failure BEFORE UPDATE ON market_stream_minutes FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='test-only'");
        try {assertThatThrownBy(()->stream.append(tick("100002","102","2","3"))).isInstanceOf(RuntimeException.class);}
        finally {jdbc.execute("DROP TRIGGER test_minute_failure");}
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM market_stream_events",Integer.class)).isEqualTo(1);
        assertThat(stream.append(tick("100002","102","2","3"))).isTrue();
        assertThat(stream.minutes("005930",MarketStreamTest.NOW.minusSeconds(100)).get(0).volume()).isEqualTo("3");
    }
    @Test void eightConcurrentDuplicateWritersCommitOneReceiptAndBarAddition() throws Exception {
        var pool=Executors.newFixedThreadPool(8);var latch=new CountDownLatch(1);
        try {
            var futures=new ArrayList<Future<Boolean>>();
            for(int i=0;i<8;i++) futures.add(pool.submit(()->{latch.await();return stream.append(tick("100001","100","2","2"));}));
            latch.countDown();int inserted=0;for(var future:futures) if(future.get(15,TimeUnit.SECONDS)) inserted++;
            assertThat(inserted).isEqualTo(1);assertThat(stream.minutes("005930",MarketStreamTest.NOW.minusSeconds(100)).get(0).volume()).isEqualTo("2");
        } finally {pool.shutdownNow();}
    }
    @Test void changedAndRevertedContentAreVersionsWhileUnchangedFetchIsDeduplicated() {
        for(String title:List.of("A","A","B","A")) feed.saveAndFind(request,List.of(article(title,"same")),List.of());
        var changes=journal.changes("005930",0,100);
        assertThat(changes).hasSize(3);assertThat(changes).extracting(ResearchJournalMapper.Version::revision).containsExactly(1L,2L,3L);
        assertThat(changes).extracting(ResearchJournalMapper.Version::changeId).containsExactly(1L,2L,3L);
        assertThat(jdbc.queryForObject("SELECT title FROM research_news",String.class)).isEqualTo("A");
    }
    @Test void firstChangedLegacyRowIsPreservedAsObservedBaselineNotInventedHistory() {
        var legacy=proxy(new ResearchFeedStore(session.getMapper(ResearchNewsMapper.class),session.getMapper(ResearchDisclosureMapper.class)));
        legacy.saveAndFind(request,List.of(article("old","same")),List.of());
        feed.saveAndFind(request,List.of(article("new","same")),List.of());
        var changes=journal.changes("005930",0,100);
        assertThat(changes).hasSize(2);assertThat(changes.get(0).origin()).isEqualTo("LEGACY_BASELINE");
        assertThat(changes.get(0).payload()).contains("old");assertThat(changes.get(1).payload()).contains("new");
    }
    @Test void checkpointFailureRollsBackVersionsHeadLatestAndClock() {
        jdbc.execute("CREATE TRIGGER test_checkpoint_failure BEFORE INSERT ON research_checkpoints FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='test-only'");
        var coverage=List.of(journal.coverage("NAVER_NEWS",request));
        try {assertThatThrownBy(()->feed.saveAndFind(request,List.of(article("A","same")),List.of(),coverage)).isInstanceOf(RuntimeException.class);}
        finally {jdbc.execute("DROP TRIGGER test_checkpoint_failure");}
        for(String table:List.of("research_versions","research_item_heads","research_news","research_checkpoints"))
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM "+table,Integer.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT last_id FROM research_journal_clock",Long.class)).isZero();
        feed.saveAndFind(request,List.of(article("A","same")),List.of(),coverage);
        assertThat(journal.changes("005930",0,100).get(0).changeId()).isEqualTo(1);
    }
    @Test void checkpointUsesOverlapAndQueryIdentityAndNeverRegresses() {
        var previous=new ResearchRequest("005930","삼성전자",request.fromDate(),LocalDate.of(2026,11,2));
        feed.saveAndFind(request,List.of(),List.of(),List.of(journal.coverage("NAVER_NEWS",previous)));
        assertThat(journal.scope("NAVER_NEWS",request).fromDate()).isEqualTo(LocalDate.of(2026,10,31));
        var oldRequest=new ResearchRequest("000660","다른 종목",LocalDate.of(2026,8,1),LocalDate.of(2026,8,2));
        var currentRequest=new ResearchRequest("000660","다른 종목",LocalDate.of(2026,10,1),request.toDate());
        feed.saveAndFind(oldRequest,List.of(),List.of(),List.of(journal.coverage("NAVER_NEWS",oldRequest)));
        assertThat(journal.scope("NAVER_NEWS",currentRequest).fromDate()).isEqualTo(LocalDate.of(2026,7,31));
        assertThat(journal.scope("OTHER",request)).isEqualTo(request);
        var renamed=new ResearchRequest("005930","다른 검색어",request.fromDate(),request.toDate());
        assertThat(journal.scope("NAVER_NEWS",renamed)).isEqualTo(renamed);
        feed.saveAndFind(request,List.of(),List.of(),List.of(journal.coverage("NAVER_NEWS",new ResearchRequest("005930","삼성전자",request.fromDate(),LocalDate.of(2026,10,1)))));
        assertThat(journal.scope("NAVER_NEWS",request).fromDate()).isEqualTo(LocalDate.of(2026,10,31));
    }
    @Test void commitOrderClockPreventsConcurrentCursorSkipping() throws Exception {
        var beforeCommit=new CountDownLatch(1);var release=new CountDownLatch(1);var pool=Executors.newFixedThreadPool(2);
        try {
            var first=pool.submit(()->new TransactionTemplate(manager).execute(status->{
                feed.saveAndFind(request,List.of(article("first","first")),List.of());beforeCommit.countDown();
                try {if(!release.await(10,TimeUnit.SECONDS)) throw new IllegalStateException();}catch(InterruptedException e){throw new IllegalStateException(e);}return null;
            }));
            assertThat(beforeCommit.await(5,TimeUnit.SECONDS)).isTrue();
            var second=pool.submit(()->feed.saveAndFind(request,List.of(article("second","second")),List.of()));
            assertThat(journal.changes("005930",0,100)).isEmpty();Thread.sleep(100);assertThat(second.isDone()).isFalse();
            release.countDown();first.get(10,TimeUnit.SECONDS);second.get(10,TimeUnit.SECONDS);
            assertThat(journal.changes("005930",0,100)).extracting(ResearchJournalMapper.Version::changeId).containsExactly(1L,2L);
            assertThat(journal.changes("005930",1,100)).extracting(ResearchJournalMapper.Version::changeId).containsExactly(2L);
        } finally {release.countDown();pool.shutdownNow();}
    }
    final Instant exportFrom = Instant.parse("2025-11-03T00:00:00Z");
    final Instant exportTo = exportFrom.plusSeconds(120);
    @Test void storedExportPreservesRawEventsResearchLineageAndGeneratesBridgeFixture() throws Exception {
        var bridgeJson = json.copy().disable(com.fasterxml.jackson.databind.SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        var bridgeStream = proxy(new MarketStreamStore(session.getMapper(MarketStreamMapper.class), bridgeJson));
        long[][] ticks = {{1,2,100,2,2},{20,70,102,3,5},{61,62,104,2,7}};
        for (var t : ticks) {
            String id = KisStreamDecoder.hash("TRADE|005930|2025-11-03|" + t[4]);
            bridgeStream.append(new MarketStreamEvent(id,"005930","TRADE",exportFrom.plusSeconds(t[0]),exportFrom.plusSeconds(t[1]),
                ""+t[2],""+t[3],""+t[4],List.of(),List.of(),"R","PROVIDER_DATE"));
        }
        bridgeStream.append(new MarketStreamEvent(KisStreamDecoder.hash("test-quote"),"005930","QUOTE",exportFrom.plusSeconds(5),exportFrom.plusSeconds(6),
            null,null,null,List.of(),List.of(),"R","RECEIVE_DATE_INFERRED"));
        for (String title : List.of("A","B","A")) feed.saveAndFind(request,List.of(new NewsArticle("NAVER_NEWS","005930",title,
            "https://news.test/bridge","요약",exportFrom.minusSeconds(86400))),List.of());
        feed.saveAndFind(request,List.of(),List.of(new Disclosure("OPEN_DART","005930","corp","테스트","정정 공시","receipt","제출자",LocalDate.of(2025,11,3),"https://dart.test/receipt")));
        jdbc.update("UPDATE research_versions SET observed_at=TIMESTAMPADD(SECOND,change_id*10,?)",LocalDateTime.ofInstant(exportFrom,ZoneOffset.UTC));
        var service = proxy(new StoredDatasetExportService(jdbc,bridgeJson));
        var result = service.export("005930",exportFrom,exportTo);
        assertThat(result.streamEvents()).hasSize(4);assertThat(result.researchVersions()).hasSize(4);
        assertThat(result.researchVersions().stream().filter(v -> v.kind().equals("NEWS"))).extracting(StoredDatasetExportService.VersionRow::revision).containsExactly(1L,2L,3L);
        assertThat(result.readOnly()).isTrue();assertThat(result.usableForTrading()).isFalse();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM market_stream_events",Integer.class)).isEqualTo(4);
        var fixture = java.nio.file.Path.of("build-codex-dataset-export/bridge-fixture.json");
        java.nio.file.Files.createDirectories(fixture.getParent());
        java.nio.file.Files.write(fixture,bridgeJson.writeValueAsBytes(com.sagopalgo.api.common.response.ApiResponse.success(result,"SYNTHETIC_TEST_ONLY")));
    }
    @Test void storedExportRejectsCorruptedResearchHashWithoutChangingRows() {
        feed.saveAndFind(request,List.of(article("A","same")),List.of());
        jdbc.update("UPDATE research_versions SET observed_at=?,content_hash=REPEAT('0',64)",LocalDateTime.ofInstant(exportFrom,ZoneOffset.UTC));
        assertThatThrownBy(()->proxy(new StoredDatasetExportService(jdbc,json)).export("005930",exportFrom,exportTo))
            .hasMessage("저장 자료의 025·026 적용 상태와 무결성을 확인하세요.");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM research_versions",Integer.class)).isEqualTo(1);
    }
    @Test void storedExportRejectsLimitBeforeLoadingPayloads() {
        var parameters = new ArrayList<Object[]>();
        for (int n=0;n<10001;n++) parameters.add(new Object[]{String.format("%064x",n),"005930","TRADE",LocalDateTime.ofInstant(exportFrom,ZoneOffset.UTC),LocalDateTime.ofInstant(exportFrom,ZoneOffset.UTC),"{}"});
        jdbc.batchUpdate("INSERT INTO market_stream_events VALUES(?,?,?,?,?,?)",parameters);
        assertThatThrownBy(()->proxy(new StoredDatasetExportService(jdbc,json)).export("005930",exportFrom,exportTo))
            .hasMessage("내보내기 상한을 초과했습니다. 일부 자료로 완료 처리하지 않습니다.");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM market_stream_events",Integer.class)).isEqualTo(10001);
    }
    @Test void exportSnapshotExcludesConcurrentCommitBetweenQueries() throws Exception {
        var pool = Executors.newSingleThreadExecutor();
        var inserted = new java.util.concurrent.atomic.AtomicBoolean();
        JdbcTemplate probe = new JdbcTemplate(source) {
            @Override public <T> T queryForObject(String sql,org.springframework.jdbc.core.RowMapper<T> mapper,Object... args) {
                T result = super.queryForObject(sql,mapper,args);
                if(sql.startsWith("SELECT COUNT") && inserted.compareAndSet(false,true)) {
                    try { pool.submit(()->{
                        feed.saveAndFind(request,List.of(article("concurrent","new")),List.of());
                        jdbc.update("UPDATE research_versions SET observed_at=?",LocalDateTime.ofInstant(exportFrom,ZoneOffset.UTC));
                    }).get(10,TimeUnit.SECONDS); } catch(Exception e) {throw new IllegalStateException(e);}
                }
                return result;
            }
        };
        try {
            var result = proxy(new StoredDatasetExportService(probe,json)).export("005930",exportFrom,exportTo);
            assertThat(result.researchVersions()).isEmpty();
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM research_versions",Integer.class)).isEqualTo(1);
        } finally {pool.shutdownNow();}
    }
}
