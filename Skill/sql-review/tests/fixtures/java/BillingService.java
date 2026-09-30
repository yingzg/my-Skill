package com.example.service;

import com.example.entity.Order;
import com.example.repository.OrderRepository;

public class BillingService {
    private final OrderRepository orderRepository;

    public BillingService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public Order loadOrder(String orderNo) {
        return orderRepository.findByOrderNo(orderNo);
    }
}
