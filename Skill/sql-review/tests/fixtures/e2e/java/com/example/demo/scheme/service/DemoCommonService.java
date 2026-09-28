package com.example.demo.scheme.service;

import com.example.demo.scheme.infra.database.mapper.democrm.DemoCommonMapper;

public class DemoCommonService {
    private final DemoCommonMapper icrmCommonMapper;

    public DemoCommonService(DemoCommonMapper icrmCommonMapper) {
        this.icrmCommonMapper = icrmCommonMapper;
    }

    public Object findCommon(String cnId) {
        return icrmCommonMapper.selectByCnId(cnId);
    }
}
