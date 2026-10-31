package com.sagopalgo.api.recommendation.service;

import com.sagopalgo.api.recommendation.mapper.AnalysisSnapshotMapper;
import com.sagopalgo.api.recommendation.mapper.RecommendationMapper;
import com.sagopalgo.api.recommendation.mapper.RecommendationReasonMapper;
import com.sagopalgo.api.recommendation.model.AnalysisSnapshotRecord;
import com.sagopalgo.api.recommendation.model.RecommendationReasonRecord;
import com.sagopalgo.api.recommendation.model.RecommendationRecord;
import com.sagopalgo.api.recommendation.model.StoredRecommendation;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 추천 본문, 근거, 분석 원문을 하나의 트랜잭션으로 저장합니다.
 */
@Service
public class RecommendationStore {

    private final RecommendationMapper recommendationMapper;
    private final RecommendationReasonMapper reasonMapper;
    private final AnalysisSnapshotMapper snapshotMapper;

    public RecommendationStore(
        RecommendationMapper recommendationMapper,
        RecommendationReasonMapper reasonMapper,
        AnalysisSnapshotMapper snapshotMapper
    ) {
        this.recommendationMapper = recommendationMapper;
        this.reasonMapper = reasonMapper;
        this.snapshotMapper = snapshotMapper;
    }

    @Transactional
    public StoredRecommendation save(
        RecommendationRecord recommendation,
        List<RecommendationReasonRecord> reasons,
        AnalysisSnapshotRecord snapshot
    ) {
        recommendationMapper.insert(recommendation);
        Long recommendationId = recommendation.getRecommendationId();
        reasons.forEach(reason -> {
            reason.setRecommendationId(recommendationId);
            reasonMapper.insert(reason);
        });
        snapshot.setRecommendationId(recommendationId);
        snapshotMapper.insert(snapshot);
        return findById(recommendation.getUserId(), recommendationId).orElseThrow();
    }

    @Transactional(readOnly = true)
    public Optional<StoredRecommendation> findById(Long userId, Long recommendationId) {
        return recommendationMapper.findByIdAndUserId(recommendationId, userId)
            .map(record -> stored(record, true));
    }

    @Transactional(readOnly = true)
    public Optional<StoredRecommendation> findLatest(Long userId) {
        return recommendationMapper.findLatestByUserId(userId)
            .map(record -> stored(record, true));
    }

    @Transactional(readOnly = true)
    public Optional<StoredRecommendation> findLatestRelevant(Long userId) {
        return recommendationMapper.findLatestRelevantByUserId(userId).map(record -> stored(record, true));
    }

    @Transactional(readOnly = true)
    public List<StoredRecommendation> findPage(
        Long userId,
        String status,
        int page,
        int size
    ) {
        return recommendationMapper.findPage(userId, status, size, page * size)
            .stream()
            .map(record -> stored(record, false))
            .toList();
    }

    @Transactional(readOnly = true)
    public long count(Long userId, String status) {
        return recommendationMapper.count(userId, status);
    }

    private StoredRecommendation stored(RecommendationRecord record, boolean includeReasons) {
        List<RecommendationReasonRecord> reasons = includeReasons
            ? reasonMapper.findByRecommendationId(record.getRecommendationId())
            : List.of();
        return new StoredRecommendation(record, reasons);
    }
}
