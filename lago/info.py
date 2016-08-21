class Info:
    @staticmethod
    def ip(prefix, requested_vms, **kwargs):
        output = []
        for vm in requested_vms:
            line = [vm.name()]
            for nic in vm.nics():
                line.append('{}:{}'.format(nic['net'], nic.get('ip', 'N/A')))
                output.append(','.join(line))
        return output
