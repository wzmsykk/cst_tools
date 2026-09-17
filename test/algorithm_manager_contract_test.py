from pathlib import Path

from csttool.cstmanager import SimulationTask
from csttool.myAlgorithm_pop import myAlg01


class ModernManagerOnly:
    """Manager double intentionally exposing no legacy queue methods."""

    def __init__(self, root: Path):
        self.currProjectDir = root
        self.result_dir = root / "result"
        self.result_dir.mkdir()
        self.executed = []
        self.batches = []

    def getResultDir(self):
        return self.result_dir

    def execute(self, task):
        self.executed.append(task)
        return {"TaskStatus": "Success", "PostProcessResult": []}

    def run_batch(self, tasks):
        tasks = list(tasks)
        self.batches.append(tasks)
        return [
            {
                "TaskStatus": "Success",
                "PostProcessResult": {
                    "name": f"abcdefghijklmnop{index}",
                    "value": index + 1,
                },
            }
            for index, _task in enumerate(tasks)
        ]

    def stop(self):
        pass


def test_algorithm_executes_named_parameter_mapping_through_simulation_task(tmp_path):
    manager = ModernManagerOnly(tmp_path)
    algorithm = myAlg01(manager=manager, params=[])
    values = [1, 700, 800, 1e-5, 20]

    result = algorithm._execute_simulation(values, "band-1", retry_count=2)

    assert result["TaskStatus"] == "Success"
    assert manager.executed == [
        SimulationTask(
            params={
                "nmodes": 1,
                "fmin": 700,
                "fmax": 800,
                "accuracy": 1e-5,
                "cell": 20,
            },
            job_name="band-1",
            retry_count=2,
        )
    ]


def test_algorithm_parallel_path_uses_run_batch_in_submission_order(tmp_path):
    manager = ModernManagerOnly(tmp_path)
    algorithm = myAlg01(manager=manager, params=[])
    algorithm.dimension_output = 1

    values = algorithm.get_y_trans_r_aprallel(
        [[1, 700, 750, 1e-5, 20], [1, 750, 800, 1e-5, 20]],
        run_count=3,
    )

    assert values.tolist() == [[1], [2]]
    assert [task.job_name for task in manager.batches[0]] == ["3700", "3750"]
    assert [task.params["fmin"] for task in manager.batches[0]] == [700, 750]
