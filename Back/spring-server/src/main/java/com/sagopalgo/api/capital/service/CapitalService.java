package com.sagopalgo.api.capital.service;

import com.sagopalgo.api.capital.dto.CapitalResponse;
import com.sagopalgo.api.capital.dto.UpdateCapitalRequest;
import com.sagopalgo.api.capital.mapper.UserCapitalMapper;
import com.sagopalgo.api.capital.model.UserCapital;
import java.math.BigDecimal;
import java.math.RoundingMode;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 사용자 자본금과 종목당 권장 투자금 계산을 담당하는 서비스입니다.
 */
@Service
public class CapitalService {

    private static final BigDecimal DEFAULT_RISK_PER_TRADE_RATE = new BigDecimal("0.0200");
    private static final BigDecimal MIN_POSITION_RATE = new BigDecimal("0.10");
    private static final BigDecimal MAX_POSITION_RATE = new BigDecimal("0.20");
    private static final int MONEY_SCALE = 2;

    private final UserCapitalMapper userCapitalMapper;

    public CapitalService(UserCapitalMapper userCapitalMapper) {
        this.userCapitalMapper = userCapitalMapper;
    }

    @Transactional(readOnly = true)
    public CapitalResponse findByUserId(Long userId) {
        UserCapital capital = userCapitalMapper.findByUserId(userId)
            .orElseGet(() -> defaultCapital(userId));
        return CapitalResponse.from(capital);
    }

    @Transactional
    public CapitalResponse update(Long userId, UpdateCapitalRequest request) {
        userCapitalMapper.lockUser(userId);
        UserCapital capital = buildCapital(
            userId,
            normalizeMoney(request.availableCapital()),
            request.riskPerTradeRate()
        );

        int updatedRows = userCapitalMapper.updateByUserId(capital);
        if (updatedRows == 0) {
            userCapitalMapper.insert(capital);
        }

        return CapitalResponse.from(capital);
    }

    public BigDecimal maxAllowedLoss(Long userId) {
        UserCapital capital = userCapitalMapper.findByUserId(userId)
            .orElseGet(() -> defaultCapital(userId));
        return capital.getAvailableCapital()
            .multiply(capital.getRiskPerTradeRate())
            .setScale(MONEY_SCALE, RoundingMode.HALF_UP);
    }

    private UserCapital defaultCapital(Long userId) {
        return buildCapital(userId, BigDecimal.ZERO.setScale(MONEY_SCALE, RoundingMode.HALF_UP), DEFAULT_RISK_PER_TRADE_RATE);
    }

    private UserCapital buildCapital(Long userId, BigDecimal availableCapital, BigDecimal riskPerTradeRate) {
        UserCapital capital = new UserCapital();
        capital.setUserId(userId);
        capital.setAvailableCapital(availableCapital);
        capital.setRiskPerTradeRate(riskPerTradeRate);
        capital.setRecommendedMinPosition(positionAmount(availableCapital, MIN_POSITION_RATE));
        capital.setRecommendedMaxPosition(positionAmount(availableCapital, MAX_POSITION_RATE));
        return capital;
    }

    private BigDecimal positionAmount(BigDecimal availableCapital, BigDecimal positionRate) {
        return availableCapital.multiply(positionRate).setScale(MONEY_SCALE, RoundingMode.HALF_UP);
    }

    private BigDecimal normalizeMoney(BigDecimal value) {
        return value.setScale(MONEY_SCALE, RoundingMode.HALF_UP);
    }
}
