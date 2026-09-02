package com.xiaomi.intl.scheme.controller;

import com.xiaomi.intl.scheme.service.IcrmCommonService;

@RestController
public class IcrmCommonController {
    private final IcrmCommonService icrmCommonService;

    public IcrmCommonController(IcrmCommonService icrmCommonService) {
        this.icrmCommonService = icrmCommonService;
    }

    public Object getCommon(String cnId) {
        return icrmCommonService.findCommon(cnId);
    }
}
