package com.sagopalgo.api.capital.mapper;

import com.sagopalgo.api.capital.model.UserCapital;
import java.util.Optional;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/**
 * user_capital 테이블에 접근하는 MyBatis Mapper입니다.
 */
@Mapper
public interface UserCapitalMapper {

    @Select("""
        SELECT capital_id, user_id, available_capital, risk_per_trade_rate,
               recommended_min_position, recommended_max_position, created_at, updated_at
        FROM user_capital
        WHERE user_id = #{userId}
        """)
    Optional<UserCapital> findByUserId(@Param("userId") Long userId);

    @Insert("""
        INSERT INTO user_capital (
            user_id, available_capital, risk_per_trade_rate,
            recommended_min_position, recommended_max_position
        )
        VALUES (
            #{userId}, #{availableCapital}, #{riskPerTradeRate},
            #{recommendedMinPosition}, #{recommendedMaxPosition}
        )
        """)
    @Options(useGeneratedKeys = true, keyProperty = "capitalId", keyColumn = "capital_id")
    int insert(UserCapital capital);

    @Update("""
        UPDATE user_capital
        SET available_capital = #{availableCapital},
            risk_per_trade_rate = #{riskPerTradeRate},
            recommended_min_position = #{recommendedMinPosition},
            recommended_max_position = #{recommendedMaxPosition}
        WHERE user_id = #{userId}
        """)
    int updateByUserId(UserCapital capital);
}
