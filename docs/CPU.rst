Lago CPU Models in detail
=========================

There are several ways you can configure the CPU model Lago will use
for each VM. This section tries to explain more in-depth how it will be 
mapped to libvirt XML.


* ``vcpu``: Number of virtual CPUs.

* ``cpu_model: <model>``: This defines an exact match of a CPU model.
  The generated Libvirt ``<cpu>`` XML will be:

  .. code-block:: xml

      <cpu>
          <model>Westmere</model>
          <topology cores="1" sockets="3" threads="1"/>
          <feature name="vmx" policy="require"/>
      </cpu>


  If the vendor of the host CPU and the selected model match, it will attempt
  to require ``vmx`` on Intel CPUs and ``svm`` on AMD CPUs, assuming the host
  CPU has that feature.
  The topology node will be generated with sockets equals to ``vcpu``
  parameter, by default it is set to ``2``.

* ``cpu_custom``: This allows to override entirely the CPU definition,
  by writing the domain CPU XML in YAML syntax, for example, for the following
  LagoInitFile:

  .. code-block:: yaml

      domains:
        vm-el73:
          vcpu: 2
          cpu_custom:
            '@mode': custom
            '@match': exact
            model:
              '@fallback': allow
              '#text': Westmere
            feature:
              '@policy': optional
              '@name': 'vmx'
            numa:
              cell:
                -
                  '@id': 0
                  '@cpus': 0
                  '@memory': 2048
                  '@unit': 'MiB'
                -
                  '@id': 1
                  '@cpus': 1
                  '@memory': 2048
                  '@unit': 'MiB'
        ...


  This will be the generated ``<cpu>`` XML:

  .. code-block:: xml


    <cpu mode="custom" match="exact">
        <model fallback="allow">Westmere</model>
        <feature policy="optional" name="vmx"/>
        <numa>
            <cell id="0" cpus="0" memory="2048" unit="MiB"/>
            <cell id="1" cpus="1" memory="2048" unit="MiB"/>
        </numa>
        <topology cores="1" sockets="2" threads="1"/>
    </cpu>
    <vcpu>2</vcpu>

  The conversion is pretty straight-forward, ``@`` maps to attribute, and
  ``#text`` to text fields. If ``topology`` section is not defined, it will be
  added.

* No ``cpu_custom`` or ``cpu_model``: Then Libvirt's ``host-passthrough`` will
  be used. For more information see: `Libvirt CPU model`_

  .. _`Libvirt CPU model`: https://libvirt.org/formatdomain.html#elementsCPU
