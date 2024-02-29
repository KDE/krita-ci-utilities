# Configuration of the KDE CI Notary Services

The `*.ini` files specify the general settings for the services and the corresponding
clients used by the KDE CI/CD pipelines. The `*-projects.yaml` files specify
the project-specific settings for the services.

For all projects that want to use some of the services, one or more branches
must be cleared for this service. This is done by adding the project and the
desired branches to the service's `*-projects.yaml` file.

The KDE CI Notary Services repository can be found [here](https://invent.kde.org/sysadmin/ci-notary-service).

## Project-specific Settings

The project-specific settings consist of two parts:
* Default settings shared by all projects (e.g. the signing key) and branches
for which the service can be used by all projects;
* Settings that are specific for a project (or a project's branch) and that
override the defaults. And branches for which the service can be used additionally
to the default branches.

All settings can be specified globally for all projects (below `defaults`),
for all branches of one project (below the project's identifier), and
for one branch of one project (below the branch name in the project settings).

The top-level project identifier must match the path of the project
([CI_PROJECT_PATH](https://invent.kde.org/help/ci/variables/predefined_variables.md))
on invent.kde.org, e.g. `pim/itinerary`.

## Project-specific Settings for Android Services

For all projects, the application ID (e.g. `org.kde.itinerary`) must be specified
as `applicationid` below the project's entry. The services verify that the
application ID matches the ID of the APK.

### apksigner

The project-specific settings are specified in `apksigner-projects.yaml`. For
all projects, APKs built from the master branch are signed. If you also want to sign
the APKs built from the latest release branch, then add the name of this branch
to the `branches` dictionary of the project's entry, e.g.

```yaml
pim/itinerary:
  applicationid: org.kde.itinerary
  branches:
    release/23.08:
```

Note that the branch below `branches` is specified as (empty) dictionary.

Additionally, you will most likely have to specify the file name of the keystore which
contains the key to sign your app and the file name of a file containing the password
protecting the keystore. Google recommends to use separate signing keys for different
apps. Submit a [sysadmin ticket](https://community.kde.org/Sysadmin) to get the keystore file on the system providing the
signing service or to ask for a new key(store) to be created for you app.

### fdroidpublisher

The project-specific settings are specified in `fdroidpublisher-projects.yaml`. For
all projects, APKs built from the master branch are published in [KDE's F-Droid Nightly
Build repository](https://community.kde.org/Android/F-Droid#KDE_F-Droid_Nightly_Build_Repository).
If you also want to publish the APKs built from the latest release branch,
then add the name of this branch to the `branches` dictionary of the project's entry.
Additionally, you have to specify the `stable-releases` repository for this branch,
so that the stable builds of your app are published in [KDE's F-Droid Release
repository](https://community.kde.org/Android/F-Droid#KDE_F-Droid_Release_Repository).

Example:
```yaml
pim/itinerary:
  applicationid: org.kde.itinerary
  branches:
    release/23.08:
      repository: stable-releases
```

### googleplaypublisher

The project-specific settings are specified in `googleplaypublisher-projects.yaml`.
By default, no branches are published on Google Play. If you want to publish the APKs
built from the latest release branch, then add the name of this branch to the `branches`
dictionary of the project's entry, e.g.

```yaml
pim/itinerary:
  applicationid: org.kde.itinerary
  branches:
    release/23.08:
```
With these settings, APKs of Itinerary built from the release branch are published
on Google Play.

All APKs are published as draft in the app's beta track, i.e. after they were
uploaded you have to release them manually via Google Play.

## Project-specific Settings for Linux Services

### flatpaksigner

The project-specific settings are specified in `flatpaksigner-projects.yaml`. For
all projects the Flatpak bundle built from the master branch is signed (or, more
precisely, the Flatpak's commit to the repository is signed). By default, the
same signing key is used for all repositories.

For all projects the application ID (e.g. `org.kde.itinerary`) must be specified
as `applicationid` below the project's entry. The services verify that the
application ID matches the application ID of the Flatpak bundle. Additionally,
you have to specify the nightly repository for the Flatpak, and optionally its runtime repo (usually on flathub).

Example:
```yaml
pim/itinerary:
  applicationid: org.kde.itinerary
  repository: itinerary-nightly
  runtimerepourl: https://dl.flathub.org/repo/flathub.flatpakrepo
```
With these settings, Flatpak bundles of Itinerary built from the default branches
(i.e. the master branch) are added to KDE's *itinerary-nightly* Flatpak repository.

#### A Note on KDE's Flatpak Repositories

As a general rule, each application should go in its own Flatpak repository.
This may seem counter intuitive from a Flatpak perspective, but, for production
stable releases, users should be retrieving those from Flathub rather than us,
so these repositories are either staging repositories for production releases,
or nightlies.

In either case, people likely only want to install a specific application or a
small group of applications - not every single KDE project.

Only exception would be if there was a collection of closely coupled applications
that should all be installed together - then those could go in the same repository.

If a Flatpak bundle is published for the first time and the target repository
does not yet exist, then the repository is created by the service.

## Project-specific Settings for Windows Services

### windowsbinariessigner

The project-specific settings are specified in `windowsbinariessigner-projects.yaml`. By
default, no projects are cleared for signing Windows binaries (executable, DLLs,
NSIS installers) and Microsoft app packages (.msix or .appx).
If you want to sign Windows binaries packaged with Craft for a branch (or multiple
branches) of your project then add an entry for your project listing the branch
(or branches) in the `branches` dictionary of the project's entry, e.g.

```yaml
utilities/kate:
  applicationid: KDEe.V.Kate
  branches:
    master:
    release/23.08:
```

With these settings, Windows binaries packaged with Craft for Kate are signed
for GitLab jobs running on the master branch and the release/23.08 branch.

The application ID (e.g. `KDEe.V.Kate`) must be specified as `applicationid`
below the project's entry. It's the value of the `Name` attribute of the `Identity`
tag in the application's `AppxManifest.xml` file. For apps published in the
Microsoft Store it's also the official application identifier. The service
verifies that the application ID matches the ID of the APPX to sign.

Note that the branches below `branches` are specified as (empty) dictionary.

### microsoftstorepublisher

The project-specific settings are specified in `microsoftstorepublisher-projects.yaml`.
By default, no branches are published on Microsoft Store. If you want to submit the APPXs
built from the latest release branch, then add the name of this branch to the `branches`
dictionary of the project's entry, e.g.

```yaml
network/neochat:
  appstreamid: org.kde.neochat
  keep:
    - keywords
  branches:
    release/23.08:
```
With these settings, APPXs of NeoChat built from the release branch are submitted
to Microsoft Store. The keywords currently used for NeoChat in Microsoft Store
are kept while all other values are updated with NeoChat's AppStream data.

The AppStream ID of the app (e.g. `org.kde.neochat`) must be specified as
`appstreamid` below the project's entry. It is used to download the AppStream data
of the app from https://apps.kde.org/appdata/. Additionally, you can specify
that some information currently published on the Microsoft Store shall not
be overwritten with information retrieved from the AppStream data by listing
the corresponding attributes below `keep`. For details, see the documentation of
microsoftstorepublisher in the sysadmin/ci-notary-service> project.

Note that the branches below `branches` are specified as (empty) dictionary.

The APPXs are submitted to Microsoft Store but the submission is not committed,
i.e. after they were uploaded you have to commit the submission manually in
the Microsoft Store to publish your app.
