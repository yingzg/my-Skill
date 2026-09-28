package com.example.demo.scheme.controller;

import com.example.demo.scheme.service.DemoCommonService;

@RestController
public class DemoCommonController {
    private final DemoCommonService icrmCommonService;

    public DemoCommonController(DemoCommonService icrmCommonService) {
        this.icrmCommonService = icrmCommonService;
    }

    public Object getCommon(String cnId) {
        return icrmCommonService.findCommon(cnId);
    }
}
