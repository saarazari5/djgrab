class Djgrab < Formula
  include Language::Python::Virtualenv

  desc "Download a song from a link into the home folder"
  homepage "https://github.com/saarazari5/djgrab"
  license "MIT"
  head "https://github.com/saarazari5/djgrab.git", branch: "master"

  # WSL is Linux, so the Linux wheels are the Windows install.
  # shortcut: Linux wheels are x86_64 only, upgrade when an ARM WSL bottle is needed

  depends_on "ffmpeg"
  depends_on "python@3.13"
  depends_on "yt-dlp"

  resource "aiofiles" do
    url "https://files.pythonhosted.org/packages/41/c3/534eac40372d8ee36ef40df62ec129bee4fdb5ad9706e58a29be53b2c970/aiofiles-25.1.0.tar.gz"
    sha256 "a8d728f0a29de45dc521f18f07297428d56992a742f0cd2701ba86e44d23d5b2"
  end

  resource "aiohappyeyeballs" do
    url "https://files.pythonhosted.org/packages/ce/f4/eec0465c2f67b2664688d0240b3212d5196fd89e741df67ddb81f8d35658/aiohappyeyeballs-2.7.1.tar.gz"
    sha256 "065665c041c42a5938ed220bdcd7230f22527fbec085e1853d2402c8a3615d9d"
  end

  resource "aiosignal" do
    url "https://files.pythonhosted.org/packages/61/62/06741b579156360248d1ec624842ad0edf697050bbaf7c3e46394e106ad1/aiosignal-1.4.0.tar.gz"
    sha256 "f47eecd9468083c2029cc99945502cb7708b082c232f9aca65da147157b251c7"
  end

  resource "aioslsk" do
    url "https://files.pythonhosted.org/packages/78/d0/92239e62403271503fb82fbbb5debb153abc7e0023387b9c4e9a303d0757/aioslsk-1.7.1.tar.gz"
    sha256 "a7565130f696f5c1c5183da05d6d943af5f174e6f77a5a1b4f80c48dfcdccaa6"
  end

  resource "annotated-types" do
    url "https://files.pythonhosted.org/packages/5f/56/a8120250d128bed162cd73c76d45f6ef9991f3e068f62a8ee060afa3104a/annotated_types-0.8.0.tar.gz"
    sha256 "13b2beaad985e05e2d6407ee4c4f35590b11f8d693a258a561055cac8f64cab7"
  end

  resource "async-upnp-client" do
    url "https://files.pythonhosted.org/packages/be/b3/289d447e1e393dd03a5bae0847886687553ab1eae87842cd8996205a8b57/async_upnp_client-0.49.0.tar.gz"
    sha256 "b2306b2277471f3d3544d688159aa98ee656306af7f203a9e48386e9a94bfbd0"
  end

  resource "attrs" do
    url "https://files.pythonhosted.org/packages/9a/8e/82a0fe20a541c03148528be8cac2408564a6c9a0cc7e9171802bc1d26985/attrs-26.1.0.tar.gz"
    sha256 "d03ceb89cb322a8fd706d4fb91940737b6642aa36998fe130a9bc96c985eff32"
  end

  resource "defusedxml" do
    url "https://files.pythonhosted.org/packages/0f/d5/c66da9b79e5bdb124974bfe172b4daf3c984ebd9c2a06e2b8a4dc7331c72/defusedxml-0.7.1.tar.gz"
    sha256 "1bb3032db185915b62d7c6209c5a8792be6a32ab2fedacc84e01b52c51aa3e69"
  end

  resource "idna" do
    url "https://files.pythonhosted.org/packages/f5/08/8eea9d4b8302028f3abb2c0813953f7aec26d33b7a8960ed760e65ff29fa/idna-3.20.tar.gz"
    sha256 "a7db850025b95ded1eae8a46181a1a6c56c92c96f0e2b005d9ff8dc0210cab44"
  end

  resource "mutagen" do
    url "https://files.pythonhosted.org/packages/df/70/1675da133ea92227da41bf5b24e1c66be597ff736a1533ade41da986852f/mutagen-1.48.1.tar.gz"
    sha256 "8f95637ab9f6f305cec6bd1294e197debe207998e3e068596563c74f86b0a173"
  end

  resource "pydantic" do
    url "https://files.pythonhosted.org/packages/7c/0b/8e10b2e693af8ec54346a14caf36221334775975a747c9ceaa3f8371d96d/pydantic-2.14.1.tar.gz"
    sha256 "94f478203dd03404682a1ada216965651dd74b1d2d5ffd62e00e0837caab5c26"
  end

  resource "pydantic-settings" do
    url "https://files.pythonhosted.org/packages/2e/3b/a5d2294799b53b448319978cfb5bd139d5a9d45e862af91661614f14c922/pydantic_settings-2.16.0.tar.gz"
    sha256 "5b6c578049ede4db0e2ef3b4eaa4ad4069cfa9211f83fb38df899dfade50a614"
  end

  resource "python-didl-lite" do
    url "https://files.pythonhosted.org/packages/5d/1a/01752557edb9a1b7f627b26c04f8642700f4cfc596d7941df027852b1aff/python_didl_lite-1.5.1.tar.gz"
    sha256 "0cdb41ee962acb369d1afb72880cab8774fc1f812ada001016346ea13e0f27b7"
  end

  resource "python-dotenv" do
    url "https://files.pythonhosted.org/packages/74/26/2fbeedb218a787a5eea551c7532cac4e009f83d689dd2faa0d0353473f86/python_dotenv-1.2.4.tar.gz"
    sha256 "f0d53e69935a851c0dcc78f3ab7aaccd8cabef0b92382b576b824212902873c0"
  end

  resource "types-aiofiles" do
    url "https://files.pythonhosted.org/packages/df/42/f5b9b90162d2196f016b87228d6bf43f2c2c0c6501bfd5415001b3eb68bb/types_aiofiles-25.1.0.20260518.tar.gz"
    sha256 "c0c95eb78755d4fa7b397d4f0332c632714dd7cd0d17f49b96e31d4d7a8d8c76"
  end

  resource "typing-extensions" do
    url "https://files.pythonhosted.org/packages/f6/cc/6253133b5bb138fc3306cebfbda2c520f545d36b5be2c7255cc528bb45d6/typing_extensions-4.16.0.tar.gz"
    sha256 "dc983d19a509c94dba722ee6abd33940f7c05a89e243c47e907eb4db6f1a43e5"
  end

  resource "typing-inspection" do
    url "https://files.pythonhosted.org/packages/a3/26/b09b8010994eccc3c09092e6b34058f36a460eea2d4c3e8b910c695975a0/typing_inspection-0.4.4.tar.gz"
    sha256 "547274fa6b0a561ccf549cc9524b999a578e737d015d8709d021f9d0d13bea47"
  end

  resource "voluptuous" do
    url "https://files.pythonhosted.org/packages/92/f4/0738e6849858deae22218be3bbb8207ba83a96e9d0ec7e8e8cd67b30e5ca/voluptuous-0.16.0.tar.gz"
    sha256 "006535e22fed944aec17bef6e8725472476194743c87bd233e912eb463f8ff05"
  end

  resource "aiohttp" do
    on_linux do
      url "https://files.pythonhosted.org/packages/32/51/395d225ef36f5a50d8e548dcd3141bfdbcd31fb6eed859022c573d2c4d66/aiohttp-3.14.5-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl"
      sha256 "1ffa3a523a36d8628f98c06492ae16a31a23d14c0b4ec721757b477319f656d6"
    end
    on_macos do
      url "https://files.pythonhosted.org/packages/15/e5/b57e58695a757fd4c02497c033fced96a69c631b13866c43d336530c9670/aiohttp-3.14.5-cp313-cp313-macosx_11_0_arm64.whl"
      sha256 "e1cc2bfaee8c214f06080a7c7d5772419b8a1108e8e5349236189811823fb02a"
    end
  end

  resource "frozenlist" do
    on_linux do
      url "https://files.pythonhosted.org/packages/d5/4e/e4691508f9477ce67da2015d8c00acd751e6287739123113a9fca6f1604e/frozenlist-1.8.0-cp313-cp313-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl"
      sha256 "fb30f9626572a76dfe4293c7194a09fb1fe93ba94c7d4f720dfae3b646b45027"
    end
    on_macos do
      url "https://files.pythonhosted.org/packages/0c/ab/6e5080ee374f875296c4243c381bbdef97a9ac39c6e3ce1d5f7d42cb78d6/frozenlist-1.8.0-cp313-cp313-macosx_11_0_arm64.whl"
      sha256 "f21f00a91358803399890ab167098c131ec2ddd5f8f5fd5fe9c9f2c6fcd91e40"
    end
  end

  resource "multidict" do
    on_linux do
      url "https://files.pythonhosted.org/packages/4d/2e/7b708a72001323dc6b2930834d63e355870ea5b1ee8d1450e0fe1a24752b/multidict-7.1.0-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl"
      sha256 "5129cc1f5fec6888e2db0be936dab67242e32c738811c8769aeea93aab4257a8"
    end
    on_macos do
      url "https://files.pythonhosted.org/packages/8c/55/477c351b21b34fe948ffffa8b64cd0c246efd998fed3de922b217e632e59/multidict-7.1.0-cp313-cp313-macosx_11_0_arm64.whl"
      sha256 "5fa1484f74d011addf2e5f5a0378ec41521989839a05d6051d8067d8ce732423"
    end
  end

  resource "propcache" do
    on_linux do
      url "https://files.pythonhosted.org/packages/ed/74/08e6c1faf26ee2732023a3828787ba535557122774f4a386b1f715cbd8e0/propcache-0.5.4-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl"
      sha256 "f85915e00dcb1cd9f2f890ead064ed40a27df06f0db65be427b29482ae357572"
    end
    on_macos do
      url "https://files.pythonhosted.org/packages/25/7d/c1ab1ef09e9d4d835be5d58c0a32a1e1de8397abaa4e502a9d4141328cad/propcache-0.5.4-cp313-cp313-macosx_11_0_arm64.whl"
      sha256 "44149f46500a0a41b95b4d99c2e586a77319539730607b9892974a092788b111"
    end
  end

  resource "pydantic-core" do
    on_linux do
      url "https://files.pythonhosted.org/packages/1c/bc/d79d000e5203ebef39af839f2ce77a777fcad6e08ad26af9a2fcd114ffc8/pydantic_core-2.50.1-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
      sha256 "17e722e156d0444ecaefbe640bdb60928752bf2013e2b7a11cdb099aaae19bec"
    end
    on_macos do
      url "https://files.pythonhosted.org/packages/f7/b9/c720e56858d4e1539503297ed37063e0c08e0f3541c41b777f6a800f75fa/pydantic_core-2.50.1-cp313-cp313-macosx_11_0_arm64.whl"
      sha256 "0c003c3b7f49debb893d2d85ae099ac5959c9839e2f330fadb1fcdf7a6594482"
    end
  end

  resource "yarl" do
    on_linux do
      url "https://files.pythonhosted.org/packages/0e/b7/a82a49bf88340b837ef6972b508a1604ae377b9e6904b46b10cf5f1cf925/yarl-1.25.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl"
      sha256 "be80550d9bfe83d9b62398a37081a90434e6df2d978ec345c3d2820de6beddab"
    end
    on_macos do
      url "https://files.pythonhosted.org/packages/a8/aa/50acc5c3e5da04172ae3c281c75405af4d2ca911e16120ab0563f4dffb66/yarl-1.25.1-cp313-cp313-macosx_11_0_arm64.whl"
      sha256 "0f12afda4eea8c8994a76d4df1875c765194f5fbe8a9d197929ea303caee29ec"
    end
  end

  def install
    # Homebrew's pip passes --no-binary=:all:, which rejects a wheel.
    venv = virtualenv_create(libexec, "python3.13")
    wheels, sources = resources.partition { |resource| resource.url.end_with?(".whl") }
    venv.pip_install sources
    python = libexec/"bin/python"
    pip = Formula["python@3.13"].opt_bin/"python3.13"
    wheels.each do |resource|
      # Already fetched before the install sandbox, which cannot download.
      system pip, "-m", "pip", "--python=#{python}", "install",
             "--disable-pip-version-check", "--no-deps", "--ignore-installed",
             resource.cached_download
    end
    venv.pip_install_and_link buildpath
  end

  test do
    output = shell_output("#{bin}/djgrab doctor")
    assert_match "yt-dlp", output
    assert_match "ffmpeg", output
  end
end
