package com.example.controller;

import com.example.entity.Order;
import com.example.service.OrderService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @Autowired
    private OrderService orderService;

    @GetMapping("/{id}")
    public Order getById(@PathVariable Long id) {
        return orderService.findById(id);
    }

    @GetMapping("/no/{orderNo}")
    public Order getByOrderNo(@PathVariable String orderNo) {
        return orderService.findByOrderNo(orderNo);
    }

    @GetMapping
    public List<Order> listAll() {
        return orderService.findAll();
    }

    @GetMapping("/search")
    public List<Order> search(
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String orderNo) {
        return orderService.findByCondition(status, orderNo);
    }

    @GetMapping("/ids")
    public List<Order> getByIds(@RequestParam List<Long> ids) {
        return orderService.findByIds(ids);
    }

    @GetMapping("/keyword")
    public List<Order> searchByKeyword(@RequestParam String keyword) {
        return orderService.findByKeyword(keyword);
    }

    @GetMapping("/mixed")
    public List<Order> searchMixed(
            @RequestParam(required = false) List<String> statusList,
            @RequestParam(required = false) Double minAmount,
            @RequestParam(required = false) Double maxAmount) {
        return orderService.findByMixed(statusList, minAmount, maxAmount);
    }
}
