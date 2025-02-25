# See https://docs.fedoraproject.org/en-US/packaging-guidelines/Python/#_example_spec_file

%define debug_package %{nil}

%define _name youtube-dl-helper
%define _name_dunder youtube_dl_helper
%define _module youtubedlhelper

%define mybuildnumber %{?build_number}%{?!build_number:1}

Name:           %{_name}
Version:        0.0.17
Release:        %{mybuildnumber}%{?dist}
Summary:        A tool to automate YouTube downloads via drag and drop

License:        GPLv3+
URL:            https://github.com/Rudd-O/%{_name}
Source:         %{_name_dunder}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel python3-setuptools
BuildRequires:  desktop-file-utils
BuildRequires:  coreutils

Requires:       (yt-dlp or youtube-dl or youtube_dl or python3-youtube_dl or python3-youtube-dl)
Requires:       (gnome-terminal or konsole5)
Requires:       gtk3
Requires:       vte291
Requires:       libnotify

%global _description %{expand:
Drag and drop URLs from your browser to this application to download YouTube
videos using youtube-dl.}

%description %_description

%prep
%autosetup -p1 -n %{_name_dunder}-%{version}

%generate_buildrequires
%pyproject_buildrequires -t


%build
%pyproject_wheel


%install
%pyproject_install

mkdir -p %{buildroot}%{_datadir}/applications
desktop-file-install --dir=%{buildroot}%{_datadir}/applications src/%{_module}/applications/%{_name}.desktop
mkdir -p %{buildroot}%{_datadir}/pixmaps
install src/%{_module}/applications/* -t %{buildroot}%{_datadir}/pixmaps

%pyproject_save_files %{_module}
echo %{_bindir}/%{_name} >> %{pyproject_files}
echo %{_datadir}/applications/%{_name}.desktop >> %{pyproject_files}
echo %{_datadir}/pixmaps/'*' >> %{pyproject_files}


%check
%tox


%files -f %{pyproject_files}

%doc README.md


%changelog
* Wed Feb 21 2024 Manuel Amador <rudd-o@rudd-o.com> 0.0.26-1
- First RPM packaging release
