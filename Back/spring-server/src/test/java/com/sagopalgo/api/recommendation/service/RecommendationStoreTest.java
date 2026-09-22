package com.sagopalgo.api.recommendation.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.recommendation.mapper.AnalysisSnapshotMapper;
import com.sagopalgo.api.recommendation.mapper.RecommendationMapper;
import com.sagopalgo.api.recommendation.mapper.RecommendationReasonMapper;
import com.sagopalgo.api.recommendation.model.AnalysisSnapshotRecord;
import com.sagopalgo.api.recommendation.model.RecommendationReasonRecord;
import com.sagopalgo.api.recommendation.model.RecommendationRecord;
import com.sagopalgo.api.recommendation.model.StoredRecommendation;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class RecommendationStoreTest {

    @Test
    @DisplayName("추천, 점수 근거, 분석 스냅샷에 같은 추천 ID를 연결한다")
    void saveConnectsGeneratedRecommendationId() {
        RecommendationMapper recommendationMapper = mock(RecommendationMapper.class);
        RecommendationReasonMapper reasonMapper = mock(RecommendationReasonMapper.class);
        AnalysisSnapshotMapper snapshotMapper = mock(AnalysisSnapshotMapper.class);
        RecommendationStore store = new RecommendationStore(
            recommendationMapper,
            reasonMapper,
            snapshotMapper
        );
        RecommendationRecord recommendation = new RecommendationRecord();
        recommendation.setUserId(1L);
        RecommendationReasonRecord reason = new RecommendationReasonRecord();
        AnalysisSnapshotRecord snapshot = new AnalysisSnapshotRecord();
        when(recommendationMapper.insert(recommendation)).thenAnswer(invocation -> {
            recommendation.setRecommendationId(42L);
            return 1;
        });
        when(recommendationMapper.findByIdAndUserId(42L, 1L))
            .thenReturn(Optional.of(recommendation));
        when(reasonMapper.findByRecommendationId(42L)).thenReturn(List.of(reason));

        StoredRecommendation stored = store.save(
            recommendation,
            List.of(reason),
            snapshot
        );

        assertThat(stored.recommendation().getRecommendationId()).isEqualTo(42L);
        assertThat(reason.getRecommendationId()).isEqualTo(42L);
        assertThat(snapshot.getRecommendationId()).isEqualTo(42L);
        verify(reasonMapper).insert(reason);
        verify(snapshotMapper).insert(snapshot);
        verify(recommendationMapper).insert(any(RecommendationRecord.class));
    }
}
