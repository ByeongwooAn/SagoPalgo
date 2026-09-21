package com.sagopalgo.api.research.client;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.ResearchProviderProperties;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.util.UriComponentsBuilder;
import org.w3c.dom.Element;
import org.xml.sax.SAXException;

/**
 * OpenDART 고유번호 파일을 한 번 내려받아 상장 종목코드와 고유번호를 연결합니다.
 */
@Component
public class OpenDartCorpCodeResolver {

    private final ResearchProviderProperties.OpenDart properties;
    private final RestClient restClient;
    private volatile Map<String, CorpCode> cachedByStockCode;

    public OpenDartCorpCodeResolver(ResearchProviderProperties properties, RestClient restClient) {
        this.properties = properties.getOpenDart();
        this.restClient = restClient;
    }

    public CorpCode resolve(String stockCode) {
        CorpCode corpCode = corpCodes().get(normalizeStockCode(stockCode));
        if (corpCode == null) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "OpenDART 고유번호에서 종목코드를 찾지 못했습니다.");
        }
        return corpCode;
    }

    private Map<String, CorpCode> corpCodes() {
        Map<String, CorpCode> snapshot = cachedByStockCode;
        if (snapshot != null) {
            return snapshot;
        }

        synchronized (this) {
            snapshot = cachedByStockCode;
            if (snapshot == null) {
                snapshot = loadCorpCodes();
                cachedByStockCode = snapshot;
            }
            return snapshot;
        }
    }

    private Map<String, CorpCode> loadCorpCodes() {
        byte[] zippedXml;
        try {
            zippedXml = restClient.get()
                .uri(UriComponentsBuilder
                    .fromUriString(endpoint(properties.getCorpCodePath()))
                    .queryParam("crtfc_key", properties.getApiKey())
                    .build()
                    .encode()
                    .toUri())
                .accept(MediaType.APPLICATION_OCTET_STREAM)
                .retrieve()
                .body(byte[].class);
        } catch (RestClientException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "OpenDART 고유번호 파일 조회에 실패했습니다.");
        }

        if (zippedXml == null || zippedXml.length == 0) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "OpenDART 고유번호 파일이 비어 있습니다.");
        }

        try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(zippedXml))) {
            ZipEntry entry = zip.getNextEntry();
            if (entry == null) {
                throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "OpenDART 고유번호 압축 파일 형식이 올바르지 않습니다.");
            }
            return parseCorpCodes(zip);
        } catch (IOException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "OpenDART 고유번호 압축 파일을 읽지 못했습니다.");
        }
    }

    private Map<String, CorpCode> parseCorpCodes(ZipInputStream xml) {
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

            var document = factory.newDocumentBuilder().parse(xml);
            var nodes = document.getElementsByTagName("list");
            Map<String, CorpCode> result = new HashMap<>();
            for (int index = 0; index < nodes.getLength(); index++) {
                Element element = (Element) nodes.item(index);
                String stockCode = childText(element, "stock_code");
                String corpCode = childText(element, "corp_code");
                if (StringUtils.hasText(stockCode) && StringUtils.hasText(corpCode)) {
                    result.put(normalizeStockCode(stockCode), new CorpCode(corpCode, childText(element, "corp_name")));
                }
            }
            return Map.copyOf(result);
        } catch (ParserConfigurationException | SAXException | IOException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "OpenDART 고유번호 XML 형식이 올바르지 않습니다.");
        }
    }

    private String childText(Element element, String tagName) {
        var nodes = element.getElementsByTagName(tagName);
        return nodes.getLength() == 0 ? "" : nodes.item(0).getTextContent().trim();
    }

    private String endpoint(String path) {
        String normalizedPath = StringUtils.hasText(path) && path.startsWith("/") ? path : "/" + path;
        return properties.getBaseUrl().replaceAll("/+$", "") + normalizedPath;
    }

    private String normalizeStockCode(String stockCode) {
        return stockCode == null ? "" : stockCode.trim();
    }

    public record CorpCode(String value, String corpName) {
    }
}
