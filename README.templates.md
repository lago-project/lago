# Templates
System  testing framework consumes templates of disk images when creating
virtual machines. Templates serve as backing images to the disks attached to 
the said virtual machines. 

## Basic concepts

### Template

Template is a versioned disk image for VMs in the testing framework. Templates 
allow having pre-initialized data inside the machine from the first boot. 
Furthermore, the 1st disk of all VMs has to be based a template (at the moment) 
to allow it booting into a working environment right away. 

Template itself is a collection of *template versions* that can be used for a 
similar goal (e.g. one such template might be 'centos7_host', a template based 
on CentOS7 and with most of the dependencies of VDSM pre-installed). 
Having different version allows updating the template (by adding newer 
versions: *v2 - added deps and updated installed packages*) while keeping in 
under the same name (centos7_host) to avoid constantly updating virt config 
manifests (that are provided to `testenvli init`).

All the information of a specific tempalte is stored inside its template
repository.

### Template version

Template version is a specific disk image that can be attached to a virtual
machine. In addition to the disk itself, template version can contain arbitrary
metadata fields. For example some, fields that are often used:

 * Distribution installed on the dist - Used to determine what target dists to 
 build for VDSM/engine/...
 * Root password - Used by engine during host-deploy stage.

### Template repository
Template repository is a manifest of all templates it provides, their versions
and sources (where the versions are stored).

Template repository itself is a JSON file containg a DOM. Here is an example
repository:
```json
{
	"name": "REPO_NAME",
	"templates": {
		"TEMPLATE_NAME_1": {
			"versions": {
				"v1": {
					"source": "SOURCE_NAME_1",
					"handle": "1/v1",
					"timestamp": 111111
				},
				"v2": {
					"source": "SOURCE_NAME_2",
					"handle": "1/v2",
					"timestamp": 222222
				}
			}
		},
		"TEMPLATE_NAME_2": {
			"versions": {
				"v1": {
					"source": "SOURCE_NAME_1",
					"handle": "2/v2",
					"timestamp": 123456
				}
			}
		}
	},
	"sources": {
		"SOURCE_NAME_1": {
			"type": "http",
			"args": {
				"baseurl": "http://www.example.com/"
			}
		}
	}
}
```

The DOM has to contain 3 fields:
 * `name` - Name of the repository
 * `templates` - Collection of all the templates it provides. This field is a
 dictionary, mapping template name to its own object.
  * Each template contains all its versions
    * Each version specifies on what source it is stored, how to get it from
    there, and how recent it is.
 * `sources` - Collection of all sources that are referenced by the templates 
 in the above collection.
  * Each source specifies its type and the arguments needed to initialize its
  provider.

### Template store

Template store is a location on the local machine (one running the testing 
framework) where the template disk images are going to be downloaded and stored
(along with their metadata). 

 * Template store should be accessible to qemu user.
 * Can be specified as parameter to `init` verb or config values.
