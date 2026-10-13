from copy import deepcopy
from pathlib import Path

import pytest

from test.support.benchmark_field_efficiency import publish_report


@pytest.mark.parametrize('change,accepted', [({},True), ({'completion':None},False),
    ({'failure':'load failure'},False), ({'numeric_validation_passed':False},False),
    ({'session':{'exit_confirmed':False,'foreign_processes':[]}},False),
    ({'session':{'exit_confirmed':True,'foreign_processes':[{'pid':123}]}},False)])
def test_all_routes_share_final_resource_status(tmp_path, change, accepted):
    report={'completion':'SUCCESS','exit_code':0,'source_unchanged':True,
            'numeric_validation_passed':True,'cst_process_seconds':1,
            'session':{'exit_confirmed':True,'foreign_processes':[]}}
    report.update(deepcopy(change))
    statuses=[]
    class Resources:
        def finish(self,status):
            statuses.append(status)
            return {'status':status}
    assert publish_report(Path(tmp_path),report,Resources()) == (0 if accepted else 1)
    assert statuses == ['Success' if accepted else 'Incomplete']
    assert report['status'] == report['resource_summary']['status']
