{
  pkgs,
  self,
  hostPkgs ? pkgs,
  qemuModule,
  ...
}:

# A fresh device accepts a configuration with only an admin user and SSH key:
# no [containers] and no [activation]. The provisioning API applies and
# commits it, first boot completes, and the admin can log in over SSH.
let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
in
nixos-lib.runTest {
  name = "users-only-provision";

  inherit hostPkgs;

  node.specialArgs = {
    inherit self;
    developmentMode = false;
    nixstasis = self.inputs.nixstasis;
  };

  nodes.gateway =
    { lib, ... }:
    {
      imports = [
        ../../modules/base.nix
        qemuModule
      ];
      system.stateVersion = "25.11";
      atomixos.rauc.enable = lib.mkForce false;
      virtualisation.memorySize = 1024;
      environment.systemPackages = [ pkgs.openssh ];
    };

  testScript = ''
    gateway.start()
    gateway.wait_for_unit("multi-user.target")
    gateway.wait_until_succeeds("curl -fsS http://127.0.0.1:8080/api/health", timeout=120)
    gateway.succeed("test ! -e /data/config/config.toml")

    gateway.succeed("ssh-keygen -q -t ed25519 -N ''' -C admin@example -f /tmp/admin-key")
    gateway.succeed(
        "printf 'version = 1\\n\\n[users.admin]\\nisAdmin = true\\nssh_key = \"%s\"\\n' "
        "\"$(cat /tmp/admin-key.pub)\" >/tmp/users-only.toml"
    )

    gateway.succeed(
        "curl -fsS -H 'Content-Type: text/plain; charset=utf-8' "
        "--data-binary @/tmp/users-only.toml http://127.0.0.1:8080/api/config "
        ">/tmp/submit.json"
    )
    gateway.succeed("jq -e '.job_url | startswith(\"/api/jobs/\")' /tmp/submit.json")
    gateway.wait_until_succeeds(
        "curl -fsS \"http://127.0.0.1:8080$(jq -r .job_url /tmp/submit.json)\" >/tmp/job.json; "
        "jq -e '.state == \"succeeded\" or .state == \"failed\"' /tmp/job.json",
        timeout=300,
    )
    print(gateway.succeed("cat /tmp/job.json"))
    gateway.succeed("jq -e '.state == \"succeeded\"' /tmp/job.json")

    # The configuration is committed with no required units or containers.
    gateway.succeed("cmp /tmp/users-only.toml /data/config/config.toml")
    gateway.succeed("jq -e '. == []' /data/config/health-required.json")
    gateway.succeed("jq -e '.required == []' /data/config/activation-policy.json")
    gateway.succeed("jq -e '.units == []' /data/config/quadlet-runtime.json")
    gateway.succeed("test ! -e /data/config.atomixos-promotion-pending")
    gateway.succeed("test ! -e /data/config-rollback")

    # First boot finishes against the users-only configuration.
    gateway.wait_until_succeeds("test -f /data/.completed_first_boot", timeout=300)

    # The admin user exists and logs in with the provisioned key.
    gateway.succeed("id admin")
    gateway.wait_for_unit("sshd.service")
    gateway.wait_until_succeeds(
        "ssh -i /tmp/admin-key -o BatchMode=yes -o StrictHostKeyChecking=no "
        "-o UserKnownHostsFile=/dev/null admin@127.0.0.1 id -un | grep -x admin",
        timeout=120,
    )
  '';
}
