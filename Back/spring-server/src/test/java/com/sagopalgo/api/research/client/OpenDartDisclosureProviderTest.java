package com.sagopalgo.api.research.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.sagopalgo.api.config.ResearchProviderProperties;
import com.sagopalgo.api.research.model.Disclosure;
import com.sagopalgo.api.research.model.ResearchRequest;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class OpenDartDisclosureProviderTest {

    private MockRestServiceServer server;
    private OpenDartDisclosureProvider provider;

    @BeforeEach
    void setUp() {
        ResearchProviderProperties properties = new ResearchProviderProperties();
        properties.getOpenDart().setEnabled(true);
        properties.getOpenDart().setBaseUrl("https://dart.test");
        properties.getOpenDart().setApiKey("dart-api-key");
        properties.getOpenDart().setPageCount(20);

        RestClient.Builder builder = RestClient.builder();
        server = MockRestServiceServer.bindTo(builder).build();
        RestClient restClient = builder.build();
        OpenDartCorpCodeResolver resolver = new OpenDartCorpCodeResolver(properties, restClient);
        provider = new OpenDartDisclosureProvider(properties, resolver, restClient);
    }

    @Test
    @DisplayName("종목코드를 DART 고유번호로 연결하고 공시를 내부 모델로 정규화한다")
    void searchResolvesCorpCodeAndNormalizesDisclosures() throws IOException {
        server.expect(requestTo("https://dart.test/api/corpCode.xml?crtfc_key=dart-api-key"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(corpCodeZip(), MediaType.APPLICATION_OCTET_STREAM));
        server.expect(requestTo("https://dart.test/api/list.json?crtfc_key=dart-api-key&corp_code=00126380&bgn_de=20250901&end_de=20250930&page_no=1&page_count=20"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess("""
                {
                  "status": "000",
                  "message": "정상",
                  "list": [
                    {
                      "corp_name": "삼성전자",
                      "report_nm": "주요사항보고서",
                      "rcept_no": "20250921000123",
                      "flr_nm": "삼성전자",
                      "rcept_dt": "20250921"
                    }
                  ]
                }
                """, MediaType.APPLICATION_JSON));

        List<Disclosure> disclosures = provider.search(new ResearchRequest(
            "005930",
            "삼성전자",
            LocalDate.of(2025, 9, 1),
            LocalDate.of(2025, 9, 30)
        ));

        assertThat(disclosures).hasSize(1);
        assertThat(disclosures.get(0).provider()).isEqualTo("OPEN_DART");
        assertThat(disclosures.get(0).corpCode()).isEqualTo("00126380");
        assertThat(disclosures.get(0).receiptDate()).isEqualTo(LocalDate.of(2025, 9, 21));
        assertThat(disclosures.get(0).link())
            .isEqualTo("https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20250921000123");
        server.verify();
    }

    private byte[] corpCodeZip() throws IOException {
        String xml = """
            <?xml version="1.0" encoding="UTF-8"?>
            <result>
              <list>
                <corp_code>00126380</corp_code>
                <corp_name>삼성전자</corp_name>
                <stock_code>005930</stock_code>
                <modify_date>20250921</modify_date>
              </list>
            </result>
            """;
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(bytes)) {
            zip.putNextEntry(new ZipEntry("CORPCODE.xml"));
            zip.write(xml.getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }
        return bytes.toByteArray();
    }
}
