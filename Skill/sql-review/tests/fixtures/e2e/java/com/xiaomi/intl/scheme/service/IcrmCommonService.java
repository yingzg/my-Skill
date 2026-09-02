package com.xiaomi.intl.scheme.service;

import com.xiaomi.intl.scheme.infra.database.mapper.icrmmscrm.IcrmCommonMapper;

public class IcrmCommonService {
    private final IcrmCommonMapper icrmCommonMapper;

    public IcrmCommonService(IcrmCommonMapper icrmCommonMapper) {
        this.icrmCommonMapper = icrmCommonMapper;
    }

    public Object findCommon(String cnId) {
        return icrmCommonMapper.selectByCnId(cnId);
    }
}
