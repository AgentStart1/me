package main

import (
	"fmt"
	"path/filepath"
	"strings"
)

// Docker permits options before and after its single context argument.
func parseBuild(args []string) (root, dockerfile string, options []string, err error) {
	boolFlags := " check compress disable-content-trust force-rm load no-cache pull push quiet rm squash "
	valueFlags := " add-host allow annotation attest build-arg build-context builder cache-from cache-to call cgroup-parent cpu-period cpu-quota cpu-shares cpuset-cpus cpuset-mems file iidfile isolation label memory memory-swap metadata-file network no-cache-filter output platform policy print progress provenance resource secret security-opt shm-size ssh tag target ulimit "
	shortNames := map[byte]string{'f': "file", 't': "tag", 'q': "quiet", 'o': "output", 'm': "memory", 'c': "cpu-shares"}
	explicitFile := ""
	positionalOnly := false
	for i := 0; i < len(args); i++ {
		arg := args[i]
		if arg == "--" && !positionalOnly {
			positionalOnly = true
			continue
		}
		if positionalOnly || !strings.HasPrefix(arg, "-") || arg == "-" {
			if root != "" {
				return "", "", nil, fmt.Errorf("exactly one build context required")
			}
			root = arg
			continue
		}
		name, value, hasValue := strings.Cut(strings.TrimPrefix(arg, "--"), "=")
		if !strings.HasPrefix(arg, "--") {
			var ok bool
			name, ok = shortNames[arg[1]]
			if !ok {
				return "", "", nil, fmt.Errorf("unsupported build option: %s", arg)
			}
			if len(arg) > 2 {
				value, hasValue = strings.TrimPrefix(arg[2:], "="), true
			}
		}
		if strings.Contains(valueFlags, " "+name+" ") {
			if !hasValue {
				i++
				if i >= len(args) {
					return "", "", nil, fmt.Errorf("missing value for %s", arg)
				}
				value = args[i]
			}
		} else if !strings.Contains(boolFlags, " "+name+" ") {
			return "", "", nil, fmt.Errorf("unsupported build option: %s", arg)
		}
		switch name {
		case "build-context", "secret", "ssh", "metadata-file", "output":
			return "", "", nil, fmt.Errorf("host-path build option --%s requires explicit transport support", name)
		case "file":
			explicitFile = value
			continue
		}
		option := "--" + name
		if hasValue || strings.Contains(valueFlags, " "+name+" ") {
			option += "=" + value
		}
		options = append(options, option)
	}
	if root == "" || root == "-" || strings.Contains(root, "://") {
		return "", "", nil, fmt.Errorf("proxy build requires a local context directory")
	}
	root, err = filepath.Abs(root)
	if err != nil {
		return
	}
	dockerfile = "Dockerfile"
	if explicitFile != "" {
		var absolute string
		absolute, err = filepath.Abs(explicitFile)
		if err != nil {
			return
		}
		dockerfile, err = filepath.Rel(root, absolute)
		if err != nil {
			return
		}
		dockerfile = filepath.ToSlash(dockerfile)
		if dockerfile == ".." || strings.HasPrefix(dockerfile, "../") {
			err = fmt.Errorf("Dockerfile must be inside the context")
			return
		}
		options = append(options, "--file="+dockerfile)
	}
	return
}
