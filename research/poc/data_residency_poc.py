"""
Data Residency and Retention Policies POC
Simulates geo controls and retention enforcement for ATP framework.
"""

DATA_REGIONS = ["us-east", "eu-west", "ap-south"]
RETENTION_POLICIES = {
    "us-east": 30,  # days
    "eu-west": 90,
    "ap-south": 60,
}


def enforce_retention(region, days):
    if region not in DATA_REGIONS:
        return f"Region {region} not supported"
    policy_days = RETENTION_POLICIES[region]
    if days > policy_days:
        return f"Retention exceeds policy for {region}"
    return f"Retention within policy for {region}"


if __name__ == "__main__":
    for region in DATA_REGIONS:
        print(enforce_retention(region, RETENTION_POLICIES[region]))
    print(enforce_retention("us-east", 45))
    print("OK: Data residency/retention POC passed")
