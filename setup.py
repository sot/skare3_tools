# Licensed under a 3-clause BSD style license - see LICENSE.rst
from setuptools import setup

try:
    from testr.setup_helper import cmdclass
except ImportError:
    cmdclass = {}

entry_points = {
    'console_scripts': [
        'skare3-test-results=skare3_tools.scripts.test_results:main',
        'skare3-release-check=skare3_tools.scripts.skare3_release_check:main',
        'gdrive=skare3_tools.gdrive.scripts.gdrive:main',
        'skare3-github-info=skare3_tools.github.scripts.ska_github_info:main',
        'skare3-dashboard=skare3_tools.dashboard.dashboard:main',
        'skare3-bulk=skare3_tools.scripts.bulk:main',
        'skare3-add-secrets=skare3_tools.github.scripts.add_secrets:main',
        'skare3-create-issue=skare3_tools.github.scripts.create_issue:main',
        'skare3-create-pr=skare3_tools.github.scripts.create_pr:main',
        'skare3-merge-pr=skare3_tools.github.scripts.merge_pr:main',
        'skare3-release-merge-info=skare3_tools.github.scripts.release_merge_info:main',
        'skare3-changes-summary=skare3_tools.scripts.skare3_update_summary:main'
    ]
}

setup(name='skare3_tools',
      author='Javier Gonzalez',
      description='Tools used for skare3 package management',
      author_email='javier.gonzalez@cfa.harvard.edu',
      packages=['skare3_tools',
                'skare3_tools.scripts',
                'skare3_tools.gdrive',
                'skare3_tools.github',
                'skare3_tools.gdrive.scripts',
                'skare3_tools.github.scripts',
                'skare3_tools.dashboard',
                'skare3_tools.tests'],
      package_data={'skare3_tools.tests': ['data/*.txt', 'data/*.dat',
                                           'data/*.fits.gz', 'data/*.pkl'],
                    'skare3_tools.gdrive': ['*.pkl'],
                    'skare3_tools.dashboard': ['static/*', 'templates/*']
                    },
      license=("New BSD/3-clause BSD License\nCopyright (c) 2019"
               " Smithsonian Astrophysical Observatory\nAll rights reserved."),
      url='http://cxc.harvard.edu/mta/ASPECT/tool_doc/pydocs/skare3_tools.html',
      entry_points=entry_points,
      use_scm_version=True,
      setup_requires=['setuptools_scm', 'setuptools_scm_git_archive'],
      zip_safe=False,
      tests_require=['pytest'],
      cmdclass=cmdclass,
      )
