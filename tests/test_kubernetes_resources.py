from pathlib import Path

import yaml


class TestKubernetesResources:
    """Test Kubernetes resource configurations for ATP deployment."""

    def test_pdb_configuration(self):
        """Test PodDisruptionBudget configuration."""
        pdb_path = Path("deploy/helm/atp/templates/pdb.yaml")
        assert pdb_path.exists(), "PDB template should exist"

        with open(pdb_path) as f:
            pdb = yaml.safe_load(f)

        assert pdb["apiVersion"] == "policy/v1"
        assert pdb["kind"] == "PodDisruptionBudget"
        assert pdb["spec"]["minAvailable"] == 2
        assert pdb["spec"]["selector"]["matchLabels"]["app"] == "atp-router"

    def test_servicemonitor_configuration(self):
        """Test ServiceMonitor configuration."""
        sm_path = Path("deploy/helm/atp/templates/servicemonitor.yaml")
        assert sm_path.exists(), "ServiceMonitor template should exist"

        with open(sm_path) as f:
            sm = yaml.safe_load(f)

        assert sm["apiVersion"] == "monitoring.coreos.com/v1"
        assert sm["kind"] == "ServiceMonitor"
        assert sm["spec"]["endpoints"][0]["port"] == "metrics"
        assert sm["spec"]["endpoints"][0]["path"] == "/metrics"

    def test_prometheusrules_configuration(self):
        """Test PrometheusRule configuration."""
        pr_path = Path("deploy/helm/atp/templates/prometheusrules.yaml")
        assert pr_path.exists(), "PrometheusRule template should exist"

        with open(pr_path) as f:
            pr = yaml.safe_load(f)

        assert pr["apiVersion"] == "monitoring.coreos.com/v1"
        assert pr["kind"] == "PrometheusRule"
        assert len(pr["spec"]["groups"][0]["rules"]) == 3

        # Check alert names
        alert_names = [rule["alert"] for rule in pr["spec"]["groups"][0]["rules"]]
        assert "ATPRouterDown" in alert_names
        assert "ATPRouterHighErrorRate" in alert_names
        assert "ATPRouterHighLatency" in alert_names

    def test_networkpolicy_configuration(self):
        """Test NetworkPolicy configuration."""
        np_path = Path("deploy/helm/atp/templates/networkpolicy.yaml")
        assert np_path.exists(), "NetworkPolicy template should exist"

        with open(np_path) as f:
            np = yaml.safe_load(f)

        assert np["apiVersion"] == "networking.k8s.io/v1"
        assert np["kind"] == "NetworkPolicy"
        assert "Ingress" in np["spec"]["policyTypes"]
        assert "Egress" in np["spec"]["policyTypes"]

    def test_resourcequota_configuration(self):
        """Test ResourceQuota configuration."""
        rq_path = Path("deploy/helm/atp/templates/resourcequota.yaml")
        assert rq_path.exists(), "ResourceQuota template should exist"

        with open(rq_path) as f:
            rq = yaml.safe_load(f)

        assert rq["apiVersion"] == "v1"
        assert rq["kind"] == "ResourceQuota"
        assert rq["spec"]["hard"]["pods"] == "20"
        assert rq["spec"]["hard"]["requests.cpu"] == "4"

    def test_hpa_configuration(self):
        """Test HorizontalPodAutoscaler configuration."""
        hpa_path = Path("deploy/helm/atp/templates/hpa.yaml")
        assert hpa_path.exists(), "HPA template should exist"

        with open(hpa_path) as f:
            hpa = yaml.safe_load(f)

        assert hpa["apiVersion"] == "autoscaling/v2"
        assert hpa["kind"] == "HorizontalPodAutoscaler"
        assert hpa["spec"]["minReplicas"] == 2
        assert hpa["spec"]["maxReplicas"] == 10

    def test_vpa_configuration(self):
        """Test VerticalPodAutoscaler configuration."""
        vpa_path = Path("deploy/helm/atp/templates/vpa.yaml")
        assert vpa_path.exists(), "VPA template should exist"

        with open(vpa_path) as f:
            vpa = yaml.safe_load(f)

        assert vpa["apiVersion"] == "autoscaling.k8s.io/v1"
        assert vpa["kind"] == "VerticalPodAutoscaler"
        assert vpa["spec"]["updatePolicy"]["updateMode"] == "Auto"

    def test_deployment_anti_affinity_and_topology_spread(self):
        """Test anti-affinity rules and topology spread constraints."""
        deployment_path = Path("deploy/helm/atp/templates/deployment.yaml")
        assert deployment_path.exists(), "Deployment template should exist"

        with open(deployment_path) as f:
            deployment = yaml.safe_load(f)

        # Check anti-affinity configuration
        affinity = deployment["spec"]["template"]["spec"]["affinity"]
        assert "podAntiAffinity" in affinity

        pod_anti_affinity = affinity["podAntiAffinity"]["preferredDuringSchedulingIgnoredDuringExecution"]

        # Should have anti-affinity for zones and hostnames
        assert len(pod_anti_affinity) == 2

        # Check zone-based anti-affinity
        zone_affinity = pod_anti_affinity[0]
        assert zone_affinity["weight"] == 100
        assert zone_affinity["podAffinityTerm"]["topologyKey"] == "topology.kubernetes.io/zone"
        assert zone_affinity["podAffinityTerm"]["labelSelector"]["matchExpressions"][0]["key"] == "app"
        assert zone_affinity["podAffinityTerm"]["labelSelector"]["matchExpressions"][0]["values"] == ["atp-router"]

        # Check hostname-based anti-affinity
        host_affinity = pod_anti_affinity[1]
        assert host_affinity["weight"] == 50
        assert host_affinity["podAffinityTerm"]["topologyKey"] == "kubernetes.io/hostname"

        # Check topology spread constraints
        topology_constraints = deployment["spec"]["template"]["spec"]["topologySpreadConstraints"]
        assert len(topology_constraints) == 2

        # Check zone-based topology spread
        zone_constraint = topology_constraints[0]
        assert zone_constraint["maxSkew"] == 1
        assert zone_constraint["topologyKey"] == "topology.kubernetes.io/zone"
        assert zone_constraint["whenUnsatisfiable"] == "DoNotSchedule"

        # Check hostname-based topology spread
        host_constraint = topology_constraints[1]
        assert host_constraint["maxSkew"] == 1
        assert host_constraint["topologyKey"] == "kubernetes.io/hostname"
        assert host_constraint["whenUnsatisfiable"] == "ScheduleAnyway"
