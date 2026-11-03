package com.sagopalgo.api.research.service;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;
import com.sagopalgo.api.config.ResearchProviderProperties;
import com.sagopalgo.api.research.client.*;
import com.sagopalgo.api.research.model.*;
import com.sagopalgo.api.research.provider.*;
import com.sagopalgo.api.research.mapper.ResearchJournalMapper;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.http.*;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class ResearchIncrementalTest {
    final ResearchRequest request=new ResearchRequest("005930","삼성전자",LocalDate.of(2026,11,1),LocalDate.of(2026,11,3));
    ResearchProviderProperties properties;
    MockRestServiceServer server;
    RestClient rest;
    @BeforeEach void setup() {
        properties=new ResearchProviderProperties();properties.getIncremental().setEnabled(true);
        properties.getNaverNews().setEnabled(true);properties.getNaverNews().setBaseUrl("https://news.test");
        properties.getNaverNews().setClientId("test-id");properties.getNaverNews().setClientSecret("test-secret");properties.getNaverNews().setDisplay(1);
        properties.getOpenDart().setEnabled(true);properties.getOpenDart().setApiKey("test-key");properties.getOpenDart().setBaseUrl("https://dart.test");properties.getOpenDart().setPageCount(1);
        var builder=RestClient.builder();server=MockRestServiceServer.bindTo(builder).build();rest=builder.build();
    }
    String news(int total,int start,String link,String date) {
        return "{\"total\":"+total+",\"start\":"+start+",\"items\":[{\"title\":\"제목\",\"originallink\":\"https://news.test/"+link+"\",\"description\":\"요약\",\"pubDate\":\""+date+"\"}]}";
    }
    void newsPage(int start,String body) {
        server.expect(r -> assertThat(r.getURI().getQuery()).contains("start="+start))
            .andRespond(withSuccess(body,MediaType.APPLICATION_JSON));
    }
    @Test void newsTraversesAllConfirmedPagesWithoutRetry() {
        newsPage(1,news(2,1,"a","Tue, 03 Nov 2026 10:00:00 +0900"));
        newsPage(2,news(2,2,"b","Mon, 02 Nov 2026 10:00:00 +0900"));
        var result=new NaverNewsProvider(properties,rest).searchBatch(request);
        assertThat(result.items()).hasSize(2);assertThat(result.complete()).isTrue();assertThat(result.pagesRead()).isEqualTo(2);server.verify();
    }
    @Test void newsSecondPageFailurePreservesFirstPageAsPartial() {
        newsPage(1,news(2,1,"a","Tue, 03 Nov 2026 10:00:00 +0900"));
        server.expect(r -> assertThat(r.getURI().getQuery()).contains("start=2")).andRespond(withStatus(HttpStatus.TOO_MANY_REQUESTS));
        var result=new NaverNewsProvider(properties,rest).searchBatch(request);
        assertThat(result.complete()).isFalse();assertThat(result.items()).hasSize(1);assertThat(result.reason()).isEqualTo("LOOKUP_FAILED");server.verify();
    }
    @Test void capAndMissingMetadataDoNotAdvanceCoverage() {
        properties.getIncremental().setMaxPages(1);
        newsPage(1,news(2,1,"a","Tue, 03 Nov 2026 10:00:00 +0900"));
        var result=new NaverNewsProvider(properties,rest).searchBatch(request);
        assertThat(result.complete()).isFalse();assertThat(result.reason()).isEqualTo("PAGE_LIMIT");
    }
    @Test void unknownPublicationTimeIsNotACompletedWindow() {
        newsPage(1,news(1,1,"a","invalid-date"));
        var result=new NaverNewsProvider(properties,rest).searchBatch(request);
        assertThat(result.complete()).isFalse();assertThat(result.items().get(0).publishedAt()).isNull();
    }
    @Test void repeatedPageAndChangingTotalRemainUnconfirmed() {
        String first=news(3,1,"a","Tue, 03 Nov 2026 10:00:00 +0900");newsPage(1,first);
        newsPage(2,first.replace("\"start\":1","\"start\":2"));
        var result=new NaverNewsProvider(properties,rest).searchBatch(request);
        assertThat(result.complete()).isFalse();assertThat(result.reason()).isEqualTo("REPEATED_PAGE");
    }
    @Test void priorDateBoundaryStopsOnlyWhenOrderingIsKnown() {
        newsPage(1,news(100,1,"old","Fri, 30 Oct 2026 10:00:00 +0900"));
        var result=new NaverNewsProvider(properties,rest).searchBatch(request);
        assertThat(result.complete()).isTrue();assertThat(result.items()).isEmpty();server.verify();
    }
    OpenDartDisclosureProvider dart() {
        var resolver=mock(OpenDartCorpCodeResolver.class);
        when(resolver.resolve("005930")).thenReturn(new OpenDartCorpCodeResolver.CorpCode("00126380","삼성전자"));
        return new OpenDartDisclosureProvider(properties,resolver,rest);
    }
    void dartPage(int page,String body) {
        server.expect(r -> assertThat(r.getURI().getQuery()).contains("page_no="+page))
            .andRespond(withSuccess(body,MediaType.APPLICATION_JSON));
    }
    String disclosure(int page,String receipt,String title) {
        return "{\"status\":\"000\",\"total_page\":2,\"page_no\":"+page+",\"list\":[{\"report_nm\":\""+title+"\",\"rcept_no\":\""+receipt+"\",\"rcept_dt\":\"20261103\"}]}";
    }
    @Test void dartPreservesSeparateCorrectionReceiptAndTraversesPages() {
        dartPage(1,disclosure(1,"20261103000001","보고서"));dartPage(2,disclosure(2,"20261103000002","[기재정정]보고서"));
        var result=dart().searchBatch(request);
        assertThat(result.complete()).isTrue();assertThat(result.items()).hasSize(2);
        assertThat(result.items().get(0).receiptNumber()).isNotEqualTo(result.items().get(1).receiptNumber());server.verify();
    }
    @Test void dartNoDataOnInitialPageIsKnownEmptyButLaterMissingPageIsNot() {
        dartPage(1,"{\"status\":\"013\"}");assertThat(dart().searchBatch(request).complete()).isTrue();
        server.reset();dartPage(1,disclosure(1,"20261103000001","보고서"));dartPage(2,"{\"status\":\"013\"}");
        var result=dart().searchBatch(request);assertThat(result.complete()).isFalse();assertThat(result.items()).hasSize(1);
    }
    @Test void partialProviderItemsAreSavedWithoutCheckpointAdvancement() {
        var provider=mock(PagedNewsProvider.class);when(provider.providerCode()).thenReturn("NAVER_NEWS");when(provider.supports(any())).thenReturn(true);
        var article=new NewsArticle("NAVER_NEWS","005930","제목","https://news.test/a","요약",Instant.now());
        when(provider.searchBatch(any())).thenReturn(new ResearchBatch<>(List.of(article),1,false,"PAGE_LIMIT"));
        var journal=mock(ResearchJournalStore.class);when(journal.scope(eq("NAVER_NEWS"),any())).thenAnswer(c->c.getArgument(1));
        var store=mock(ResearchFeedStore.class);when(store.saveAndFind(any(),anyList(),anyList(),anyList())).thenReturn(new StoredResearchFeed(List.of(article),List.of()));
        var service=new ResearchFeedService(List.of(provider),List.of(),properties,store,journal);
        var response=service.syncFeed("005930","삼성전자",null,null);
        assertThat(response.providers().get(0).status()).isEqualTo("PARTIAL");
        assertThat(response.providers().get(0).complete()).isFalse();
        verify(store).saveAndFind(any(),eq(List.of(article)),eq(List.of()),eq(List.of()));
        verify(journal,never()).coverage(any(),any());
    }
    @Test void completeProviderAdvancesOnlyAfterStoreTransaction() {
        var provider=mock(PagedNewsProvider.class);when(provider.providerCode()).thenReturn("NAVER_NEWS");when(provider.supports(any())).thenReturn(true);
        when(provider.searchBatch(any())).thenReturn(new ResearchBatch<>(List.of(),1,true,null));
        var journal=mock(ResearchJournalStore.class);when(journal.scope(any(),any())).thenAnswer(c->c.getArgument(1));
        var coverage=new ResearchJournalMapper.Coverage("NAVER_NEWS","005930","scope",LocalDate.now());when(journal.coverage(any(),any())).thenReturn(coverage);
        var store=mock(ResearchFeedStore.class);when(store.saveAndFind(any(),anyList(),anyList(),anyList())).thenReturn(new StoredResearchFeed(List.of(),List.of()));
        new ResearchFeedService(List.of(provider),List.of(),properties,store,journal).syncFeed("005930","삼성전자",null,null);
        verify(store).saveAndFind(any(),eq(List.of()),eq(List.of()),eq(List.of(coverage)));
        var order=inOrder(journal,provider,store);order.verify(journal).verify();order.verify(journal).scope(any(),any());
        order.verify(provider).searchBatch(any());order.verify(journal).coverage(any(),any());order.verify(store).saveAndFind(any(),any(),any(),any());
    }
}
