"""Test pod distribution testing functionality."""

from unittest.mock import patch

from tools.pod_distribution_tester import DistributionMetrics, PodDistributionTester, PodInfo


class TestPodDistributionTester:
    """Test the pod distribution testing functionality."""

    def test_get_pod_distribution_success(self):
        """Test successful pod distribution retrieval."""
        tester = PodDistributionTester()

        mock_output = """{
            "items": [
                {
                    "metadata": {"name": "atp-router-123"},
                    "status": {"phase": "Running"},
                    "spec": {"nodeName": "node-1"}
                },
                {
                    "metadata": {"name": "atp-router-456"},
                    "status": {"phase": "Running"},
                    "spec": {"nodeName": "node-2"}
                }
            ]
        }"""

        with patch.object(tester, "run_kubectl_command") as mock_kubectl:
            mock_kubectl.return_value = mock_output

            with patch.object(tester, "get_node_zone") as mock_zone:
                mock_zone.return_value = "us-west1-a"

                pods = tester.get_pod_distribution()

                assert len(pods) == 2
                assert pods[0].name == "atp-router-123"
                assert pods[0].node == "node-1"
                assert pods[0].zone == "us-west1-a"
                assert pods[1].name == "atp-router-456"

    def test_get_pod_distribution_no_pods(self):
        """Test handling when no pods are found."""
        tester = PodDistributionTester()

        with patch.object(tester, "run_kubectl_command") as mock_kubectl:
            mock_kubectl.return_value = '{"items": []}'

            pods = tester.get_pod_distribution()
            assert pods == []

    def test_get_node_zone_success(self):
        """Test successful node zone retrieval."""
        tester = PodDistributionTester()

        with patch.object(tester, "run_kubectl_command") as mock_kubectl:
            mock_kubectl.return_value = "us-central1-b\n"

            zone = tester.get_node_zone("node-1")
            assert zone == "us-central1-b"

    def test_calculate_distribution_metrics(self):
        """Test distribution metrics calculation."""
        tester = PodDistributionTester()

        pods = [
            PodInfo("pod-1", "node-1", "zone-a", "Running"),
            PodInfo("pod-2", "node-2", "zone-a", "Running"),
            PodInfo("pod-3", "node-3", "zone-b", "Running"),
        ]

        metrics = tester.calculate_distribution_metrics(pods)

        assert metrics.total_pods == 3
        assert metrics.nodes_used == 3
        assert metrics.zones_used == 2
        assert metrics.pods_per_node["node-1"] == 1
        assert metrics.pods_per_node["node-2"] == 1
        assert metrics.pods_per_node["node-3"] == 1
        assert metrics.pods_per_zone["zone-a"] == 2
        assert metrics.pods_per_zone["zone-b"] == 1

    def test_calculate_spread_score(self):
        """Test spread score calculation."""
        tester = PodDistributionTester()

        # Perfect spread: [2, 2, 2]
        perfect_counts = [2, 2, 2]
        perfect_score = tester._calculate_spread_score(perfect_counts)
        assert perfect_score == 0.0

        # Poor spread: [5, 1, 0]
        poor_counts = [5, 1, 0]
        poor_score = tester._calculate_spread_score(poor_counts)
        assert poor_score > 0.0

    def test_test_distribution_constraints_pass(self):
        """Test distribution constraint validation - pass case."""
        tester = PodDistributionTester()

        metrics = DistributionMetrics(
            total_pods=4,
            nodes_used=3,
            zones_used=2,
            pods_per_node={"node-1": 2, "node-2": 1, "node-3": 1},
            pods_per_zone={"zone-a": 2, "zone-b": 2},
            zone_spread_score=0.5,
            node_spread_score=0.8,
        )

        success = tester.test_distribution_constraints(metrics)
        assert success is True

    def test_test_distribution_constraints_fail(self):
        """Test distribution constraint validation - fail case."""
        tester = PodDistributionTester()

        metrics = DistributionMetrics(
            total_pods=4,
            nodes_used=1,  # Only 1 node - should fail
            zones_used=1,  # Only 1 zone - should fail
            pods_per_node={"node-1": 4},
            pods_per_zone={"zone-a": 4},
            zone_spread_score=0.0,
            node_spread_score=0.0,
        )

        success = tester.test_distribution_constraints(metrics)
        assert success is False

    @patch("tools.pod_distribution_tester.PodDistributionTester.get_pod_distribution")
    @patch("tools.pod_distribution_tester.PodDistributionTester.calculate_distribution_metrics")
    @patch("tools.pod_distribution_tester.PodDistributionTester.print_distribution_report")
    @patch("tools.pod_distribution_tester.PodDistributionTester.test_distribution_constraints")
    @patch("sys.exit")
    def test_main_flow(self, mock_exit, mock_test_constraints, mock_print_report, mock_calc_metrics, mock_get_pods):
        """Test the main execution flow."""
        mock_get_pods.return_value = [PodInfo("pod-1", "node-1", "zone-a", "Running")]
        mock_calc_metrics.return_value = DistributionMetrics(1, 1, 1, {}, {}, 0.0, 0.0)
        mock_test_constraints.return_value = True

        with patch("sys.argv", ["pod_distribution_tester.py", "--test-only"]):
            from tools.pod_distribution_tester import main

            main()

        mock_get_pods.assert_called_once()
        mock_calc_metrics.assert_called_once()
        mock_print_report.assert_not_called()  # --test-only flag
        mock_test_constraints.assert_called_once()
        mock_exit.assert_called_once_with(0)
