package com.example.repository;

import com.example.entity.Order;

public interface OrderRepository {
    Order findByOrderNo(String orderNo);
}
