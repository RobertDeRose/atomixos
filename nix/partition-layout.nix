{
  boot = {
    startMiB = 16;
    sizeMiB = 128;
    type = "xbootldr";
    typeGuid = "BC13C2FF-59E6-4262-A352-B275FD6F7172";
    labels = {
      a = "boot-a";
      b = "boot-b";
    };
  };
  rootfs = {
    startMiB = 144;
    sizeMiB = 1024;
    type = "root-arm64";
    typeGuid = "B921B045-1DF0-41C3-AF44-4C6F280D3FAE";
    labels = {
      a = "rootfs-a";
      b = "rootfs-b";
    };
  };
  data = {
    minSizeMiB = 64;
    type = "linux-generic";
    label = "data";
  };
  gptTailSlackMiB = 2;
}
