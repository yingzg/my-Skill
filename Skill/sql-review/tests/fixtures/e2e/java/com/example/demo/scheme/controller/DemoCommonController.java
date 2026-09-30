package com.example.demo.scheme.controller;

import com.example.demo.scheme.service.DemoCommonService;

@RestController
public class DemoCommonController {
    private final DemoCommonService demoCommonService;

    public DemoCommonController(DemoCommonService demoCommonService) {
        this.demoCommonService = demoCommonService;
    }

    public Object getCommon(String cnId) {
        return demoCommonService.findCommon(cnId);
    }
}
