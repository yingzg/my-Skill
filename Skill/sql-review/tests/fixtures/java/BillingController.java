package com.example.controller;

import com.example.entity.Order;
import com.example.service.BillingService;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BillingController {
    private final BillingService billingService;

    public BillingController(BillingService billingService) {
        this.billingService = billingService;
    }

    public Order getBillingOrder(String orderNo) {
        return billingService.loadOrder(orderNo);
    }
}
