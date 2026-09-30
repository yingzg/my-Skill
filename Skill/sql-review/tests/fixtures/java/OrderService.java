package com.example.service;

import com.example.entity.Order;
import com.example.mapper.OrderMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class OrderService {

    @Autowired
    private OrderMapper orderMapper;

    public Order findById(Long id) {
        return orderMapper.findById(id);
    }

    public Order findByOrderNo(String orderNo) {
        return orderMapper.findByOrderNo(orderNo);
    }

    public List<Order> findAll() {
        return orderMapper.findAll();
    }

    public List<Order> findByCondition(String status, String orderNo) {
        return orderMapper.findByCondition(status, orderNo);
    }

    public List<Order> findByIds(List<Long> ids) {
        return orderMapper.findByIds(ids);
    }

    public List<Order> findByKeyword(String keyword) {
        return orderMapper.findByKeyword(keyword);
    }

    public List<Order> findByMixed(List<String> statusList, Double minAmount, Double maxAmount) {
        return orderMapper.findByMixed(statusList, minAmount, maxAmount);
    }
}
