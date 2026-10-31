package com.sagopalgo.api.order.client;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import java.math.BigDecimal;
import org.junit.jupiter.api.*;
import org.springframework.http.*;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.*;

class KbManualOrderTransportTest {
    SecuritiesProviderProperties properties=new SecuritiesProviderProperties();
    MockRestServiceServer server;
    KbSecuritiesAccountClient client;
    @BeforeEach void setup(){
        var kb=properties.getKb();kb.setBaseUrl("https://developer.kbsec.com:32484");kb.setTokenPath("/oauth2/token");
        kb.setAppKey("test-key");kb.setAppSecret("test-secret");kb.setAccountEnabled(true);kb.setOrderEnabled(true);kb.setLiveOrderEnabled(true);
        kb.setOrderIpAddress("192.0.2.10");kb.setOrderMacAddress("02:11:22:33:44:55");
        RestClient.Builder builder=RestClient.builder();server=MockRestServiceServer.bindTo(builder).build();
        client=new KbSecuritiesAccountClient(properties,builder.build());
    }
    @Test void sendsExactOfficialHeadersAndLimitBodyOnce(){
        token();
        server.expect(requestTo("https://developer.kbsec.com:32484/api/v1/ssam1802"))
            .andExpect(method(HttpMethod.POST)).andExpect(header("Authorization","bearer test-token"))
            .andExpect(header("appKey","test-key"))
            .andExpect(content().json("""
                {"dataHeader":{"ipAddr":"192.0.2.10","macAddr":"02:11:22:33:44:55"},
                "dataBody":{"mkt_tm_clsf":"1","is_cd":"005930","ordr_q":"1","ordr_uprc":"100","ordr_ccd":"00","sor_ordr_ccd":"K"}}
                """,true))
            .andRespond(withSuccess("""
                {"dataHeader":{"resultCode":"200","processFlag":"A"},"dataBody":{"ordr_no":"0040000638"}}
                """,MediaType.APPLICATION_JSON));
        assertThat(client.sendOrderOnce(request()).status()).isEqualTo(KbLimitOrderContract.Status.ACCEPTED);server.verify();
    }
    @Test void httpFailureDoesNotRefreshTokenOrRetryOrder(){
        token();server.expect(requestTo("https://developer.kbsec.com:32484/api/v1/ssam1802")).andRespond(withServerError());
        assertThatThrownBy(()->client.sendOrderOnce(request())).isInstanceOf(RestClientException.class);server.verify();
    }
    @Test void liveSwitchOffOrDifferentHostPreventsEvenAuthentication(){
        properties.getKb().setLiveOrderEnabled(false);
        assertThatThrownBy(()->client.sendOrderOnce(request())).isInstanceOf(RuntimeException.class);
        properties.getKb().setLiveOrderEnabled(true);properties.getKb().setBaseUrl("https://other.example");
        assertThatThrownBy(()->client.sendOrderOnce(request())).isInstanceOf(RuntimeException.class);server.verify();
    }
    private void token(){server.expect(requestTo("https://developer.kbsec.com:32484/oauth2/token")).andRespond(withSuccess(
        "{\"access_token\":\"test-token\",\"expires_in\":3600}",MediaType.APPLICATION_JSON));}
    private KbLimitOrderContract.Request request(){return KbLimitOrderContract.encode(new com.sagopalgo.api.order.dto.OrderPrecheckRequest(
        "005930","삼성전자","KOSPI","BUY",new BigDecimal("100"),BigDecimal.ONE));}
}
