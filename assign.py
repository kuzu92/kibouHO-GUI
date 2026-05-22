import sys
import random
import yaml
import argparse
import itertools

def parse_arguments():
    parser = argparse.ArgumentParser(description="Role Assigner CLI")
    parser.add_argument('--mode', type=str, required=True, help='Assignment mode')
    parser.add_argument('--roles', type=str, required=True, help='Roles YAML string')
    parser.add_argument('--prefs', type=str, required=True, help='Preferences YAML string')
    return parser.parse_args()

def solve_satisfaction_first(preferences, role_counts):
    assignments = {member: None for member in preferences.keys()}
    remaining_roles = role_counts.copy()
    
    all_ranks = [r for prefs in preferences.values() if prefs for r in prefs.values()]
    max_rank = max(all_ranks) if all_ranks else 1

    for rank in range(1, max_rank + 1):
        role_demands = {role: [] for role in role_counts.keys()}
        for member, prefs in preferences.items():
            if assignments[member] is not None:
                continue
            desired_roles = [role for role, r in prefs.items() if r == rank]
            for role in desired_roles:
                if role in role_demands:
                    role_demands[role].append(member)

        active_roles = [r for r, count in remaining_roles.items() if count > 0 and len(role_demands[r]) > 0]
        sorted_roles = sorted(
            active_roles,
            key=lambda r: len(role_demands[r]) / remaining_roles[r],
            reverse=True
        )

        for role in sorted_roles:
            candidates = role_demands[role]
            valid_candidates = [c for c in candidates if assignments[c] is None]
            if not valid_candidates:
                continue
            
            random.shuffle(valid_candidates)
            available_slots = remaining_roles[role]
            chosen_members = valid_candidates[:available_slots]

            for member in chosen_members:
                assignments[member] = (role, rank, False)
                remaining_roles[role] -= 1

    _assign_unfilled(assignments, remaining_roles)
    return assignments

def solve_fairness_first(preferences, role_counts):
    members = list(preferences.keys())
    flat_roles = []
    for role, count in role_counts.items():
        flat_roles.extend([role] * count)
        
    if len(members) != len(flat_roles):
        print("【注意】人数と総定員が一致しないため、第1希望最優先モードで代用します。")
        return solve_satisfaction_first(preferences, role_counts)

    best_patterns = []
    min_max_penalty = float('inf')
    min_total_penalty = float('inf')

    seen_combinations = set()
    for p in itertools.permutations(flat_roles):
        if p in seen_combinations:
            continue
        seen_combinations.add(p)
        
        current_max_penalty = 0
        current_total_penalty = 0
        current_pattern = {}

        for member, role in zip(members, p):
            rank = preferences[member].get(role, 99)
            current_pattern[member] = (role, rank, rank == 99)
            
            penalty = rank ** 4 if rank != 99 else 10000
            current_total_penalty += penalty
            if penalty > current_max_penalty:
                current_max_penalty = penalty

        if current_max_penalty < min_max_penalty:
            min_max_penalty = current_max_penalty
            min_total_penalty = current_total_penalty
            best_patterns = [current_pattern]
        elif current_max_penalty == min_max_penalty:
            if current_total_penalty < min_total_penalty:
                min_total_penalty = current_total_penalty
                best_patterns = [current_pattern]
            elif current_total_penalty == min_total_penalty:
                best_patterns.append(current_pattern)

    return random.choice(best_patterns)

def _assign_unfilled(assignments, remaining_roles):
    unassigned_members = [m for m, r in assignments.items() if r is None]
    unfilled_roles = [r for r, count in remaining_roles.items() if count > 0]
    for member in unassigned_members:
        if unfilled_roles:
            spare_role = unfilled_roles
            assignments[member] = (spare_role, None, True)
            remaining_roles[spare_role] -= 1
            if remaining_roles[spare_role] == 0:
                unfilled_roles.pop(0)

def main():
    args = parse_arguments()
    
    try:
        roles = yaml.safe_load(args.roles)
        preferences = yaml.safe_load(args.prefs)
    except yaml.YAMLError as e:
        print(f"入力データの解析に失敗しました。形式を確認してください。\nError: {e}")
        sys.exit(1)

    total_slots = sum(roles.values()) if roles else 0
    total_people = len(preferences) if preferences else 0
    if total_slots != total_people:
        print(f"【警告】総定員({total_slots}人)とメンバー数({total_people}人)が一致していません。\n")

    if args.mode == "fairness_first":
        results = solve_fairness_first(preferences, roles)
    else:
        results = solve_satisfaction_first(preferences, roles)

    print(f"=== 役職割り当て結果 ({'ワースト回避モード' if args.mode == 'fairness_first' else '第1希望最優先モード'}) ===")
    print(f"{'名前':<10} | {'割り当て役職':<15}")
    print("-" * 35)
    for name, (role, rank, is_out_of_bounds) in results.items():
        if is_out_of_bounds:
            display_role = f"{role} (希望外分配)"
        else:
            display_role = f"{role} ({rank}希望)"
        print(f"{name:<10} | {display_role:<15}")

if __name__ == "__main__":
    main()
