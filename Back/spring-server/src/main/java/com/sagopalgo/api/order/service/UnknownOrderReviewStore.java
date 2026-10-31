package com.sagopalgo.api.order.service;
import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.order.mapper.*;
import com.sagopalgo.api.order.mapper.UnknownOrderReviewMapper.*;
import com.sagopalgo.api.order.model.ManualOrderCommand;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
@Service
public class UnknownOrderReviewStore {
    private final ManualOrderMapper commands;
    private final UnknownOrderReviewMapper reviews;
    private final OrderAccountBinding binding;
    public UnknownOrderReviewStore(ManualOrderMapper commands,UnknownOrderReviewMapper reviews,OrderAccountBinding binding){this.commands=commands;this.reviews=reviews;this.binding=binding;}
    @Transactional(propagation=Propagation.REQUIRES_NEW)
    public void prepare(PreparationRow row) {
        var c=lock(row.userId(),row.commandId());validate(c);
        if(!c.accountFingerprint().equals(row.accountFingerprint())) throw invalid();
        reviews.prepare(row);
    }
    @Transactional(propagation=Propagation.REQUIRES_NEW)
    public ReviewRow confirm(PreparationRow fresh) {
        var c=lock(fresh.userId(),fresh.commandId());
        var previous=reviews.find(fresh.reviewId(),fresh.userId(),fresh.commandId());
        if(previous!=null){if(!sameToken(previous.tokenHash(),fresh.tokenHash())) throw invalid();return previous;}
        validate(c);
        var consume=new PreparationRow(fresh.commandId(),fresh.userId(),fresh.reviewId(),fresh.accountFingerprint(),fresh.tokenHash(),
            fresh.evidenceHash(),fresh.evidenceJson(),fresh.expiresAt(),now());
        if(!c.accountFingerprint().equals(fresh.accountFingerprint()) || reviews.consume(consume)!=1) throw invalid();
        var row=new ReviewRow(fresh.reviewId(),fresh.commandId(),fresh.userId(),fresh.accountFingerprint(),fresh.tokenHash(),fresh.evidenceJson(),now());
        if(reviews.insert(row)!=1) throw new ApiException(ErrorCode.REVIEW_STORAGE_UNAVAILABLE);
        return reviews.find(row.reviewId(),row.userId(),row.commandId());
    }
    private ManualOrderCommand lock(Long user,String id) {
        if(commands.lockUser(user)==null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        var c=commands.lockCommand(id,user);if(c==null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);return c;
    }
    private void validate(ManualOrderCommand c) {
        UnknownOrderReviewRules.candidate(c.status());
        if(!binding.matches(c.accountFingerprint()) || commands.reconciliation(c.commandId(),c.userId())!=null) throw invalid();
        requireParent(commands,c);
    }
    static String requireParent(ManualOrderMapper commands,ManualOrderCommand c) {
        if("NEW".equals(c.kind())) return "";
        if(!java.util.Set.of("AMEND","CANCEL").contains(c.kind()) || c.parentId()==null) throw invalid();
        var parent=commands.find(c.parentId(),c.userId());
        if(parent==null || !"NEW".equals(parent.kind()) || !"ACCEPTED".equals(parent.status())
            || !c.commandId().equals(parent.changeId()) || !c.accountFingerprint().equals(parent.accountFingerprint())
            || !c.orderDate().equals(parent.orderDate()) || !c.stockCode().equals(parent.stockCode()) || !c.side().equals(parent.side())
            || !c.market().equals(parent.market()) || ("CANCEL".equals(c.kind()) && c.price().compareTo(parent.price())!=0)
            || ("AMEND".equals(c.kind()) && c.price().compareTo(parent.price())>=0)
            || c.quantity().compareTo(parent.quantity())!=0) throw invalid();
        UnknownOrderReviewRules.number(parent.orderNo());return parent.orderNo();
    }
    static boolean sameToken(String a,String b){return a!=null && b!=null && MessageDigest.isEqual(a.getBytes(StandardCharsets.US_ASCII),b.getBytes(StandardCharsets.US_ASCII));}
    static LocalDateTime now(){return LocalDateTime.now(ZoneId.of("Asia/Seoul"));}
    private static ApiException invalid(){return new ApiException(ErrorCode.VALIDATION_ERROR,"대조 확인이 만료·변경되었거나 원주문·계좌 조건이 맞지 않습니다. 다시 준비하세요.");}
}
