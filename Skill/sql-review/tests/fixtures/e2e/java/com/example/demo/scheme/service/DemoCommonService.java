package com.example.demo.scheme.service;

import com.example.demo.scheme.infra.database.mapper.democrm.DemoCommonMapper;

public class DemoCommonService {
    private final DemoCommonMapper demoCommonMapper;

    public DemoCommonService(DemoCommonMapper demoCommonMapper) {
        this.demoCommonMapper = demoCommonMapper;
    }

    public Object findCommon(String cnId) {
        return demoCommonMapper.selectByCnId(cnId);
    }
}
