"""HR employee filters: every filter, and every combination the spec calls out.

These assert the database result, not the rendered control: a filter that looks
present but returns unfiltered rows fails here.
"""
import pytest

DEPARTMENTS = [
    "Teaching", "Marketing", "Digital Marketing", "Managers",
    "HR", "Internship", "Senior HR",
]


@pytest.fixture(scope="module")
def lookups(client, hr_headers, employee_a, employee_b, intern_ds, intern_cy):
    """Depends on the employee fixtures so the directory has rows to filter."""
    depts = client.get("/api/departments", headers=hr_headers).json()
    depts = depts["items"] if isinstance(depts, dict) else depts
    bgs = client.get("/api/internship-backgrounds", headers=hr_headers).json()
    bgs = bgs["items"] if isinstance(bgs, dict) else bgs
    return {
        "dept_by_name": {d["name"]: d["id"] for d in depts},
        "departments": depts,
        "backgrounds": bgs,
    }


def rows(client, hr_headers, **params):
    params.setdefault("page_size", 100)
    response = client.get("/api/employees", headers=hr_headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"]


# ------------------------------------------------------------ dropdown values
def test_department_dropdown_has_every_expected_value(lookups):
    names = [d["name"] for d in lookups["departments"]]
    for expected in DEPARTMENTS:
        assert expected in names, f"missing department: {expected}"
    assert len(names) == len(set(names)), "department list must not contain duplicates"
    assert all(n and n.lower() not in ("none", "null", "undefined") for n in names)


def test_internship_background_dropdown_is_populated(lookups):
    names = [b["name"] for b in lookups["backgrounds"]]
    for expected in ("Data Science", "Cyber Security", "Web Development"):
        assert expected in names, f"missing background: {expected}"
    assert len(names) == len(set(names))
    assert all(n and n.lower() not in ("none", "null", "undefined") for n in names)


# ------------------------------------------------------------ single filters
@pytest.mark.parametrize("dept_name", DEPARTMENTS)
def test_each_department_filters_correctly(client, hr_headers, lookups, dept_name):
    dept_id = lookups["dept_by_name"][dept_name]
    result = rows(client, hr_headers, department_id=dept_id)
    assert all(r["department"] == dept_name for r in result), (
        f"{dept_name} filter returned other departments"
    )


def test_all_departments_returns_everyone(client, hr_headers, lookups):
    everyone = rows(client, hr_headers)
    one_dept = rows(client, hr_headers, department_id=lookups["dept_by_name"]["Marketing"])
    assert len(everyone) >= len(one_dept)
    assert len({r["department"] for r in everyone}) > 1


def test_employee_type_intern(client, hr_headers, lookups):
    interns = rows(client, hr_headers, employee_type="Intern")
    assert interns, "expected at least one intern"
    assert all(r["department"] == "Internship" for r in interns)


def test_employee_type_regular_excludes_interns(client, hr_headers, lookups):
    regular = rows(client, hr_headers, employee_type="Regular")
    assert regular
    assert all(r["department"] != "Internship" for r in regular)


def test_employee_type_partitions_the_directory(client, hr_headers, lookups):
    interns = {r["id"] for r in rows(client, hr_headers, employee_type="Intern")}
    regular = {r["id"] for r in rows(client, hr_headers, employee_type="Regular")}
    everyone = {r["id"] for r in rows(client, hr_headers)}
    assert not (interns & regular)
    assert interns | regular == everyone


def test_invalid_employee_type_is_rejected(client, hr_headers, lookups):
    response = client.get("/api/employees", headers=hr_headers,
                          params={"employee_type": "Contractor"})
    assert response.status_code == 422
    assert "Intern" in response.json()["detail"]


def test_internship_background_filter(client, hr_headers, lookups):
    interns = rows(client, hr_headers, employee_type="Intern")
    with_bg = [r for r in interns if r.get("internship_background")]
    assert with_bg, "expected seeded interns to carry a background"
    name = with_bg[0]["internship_background"]
    bg_id = next(b["id"] for b in lookups["backgrounds"] if b["name"] == name)

    result = rows(client, hr_headers, internship_background_id=bg_id)
    assert result
    assert all(r["internship_background"] == name for r in result)


def test_background_with_no_interns_returns_empty(client, hr_headers, lookups):
    used = {r.get("internship_background") for r in rows(client, hr_headers,
                                                         employee_type="Intern")}
    unused = [b for b in lookups["backgrounds"] if b["name"] not in used]
    if not unused:
        pytest.skip("every background has interns in this dataset")
    result = rows(client, hr_headers, internship_background_id=unused[0]["id"])
    assert result == []


def test_status_filter(client, hr_headers, lookups):
    active = rows(client, hr_headers, employment_status="Active")
    assert active
    assert all(r["employment_status"] == "Active" for r in active)


# ------------------------------------------------------------ combinations
def test_department_plus_search(client, hr_headers, lookups):
    dept_id = lookups["dept_by_name"]["Digital Marketing"]
    everyone = rows(client, hr_headers, department_id=dept_id)
    assert everyone
    needle = everyone[0]["full_name"].split()[0]

    result = rows(client, hr_headers, department_id=dept_id, search=needle)
    assert result
    for r in result:
        assert r["department"] == "Digital Marketing"
        assert needle.lower() in (r["full_name"] + r["employee_code"] +
                                  (r.get("email") or "")).lower()


def test_department_plus_status(client, hr_headers, lookups):
    dept_id = lookups["dept_by_name"]["HR"]
    result = rows(client, hr_headers, department_id=dept_id, employment_status="Active")
    assert all(r["department"] == "HR" and r["employment_status"] == "Active"
               for r in result)


def test_intern_plus_background(client, hr_headers, lookups):
    interns = rows(client, hr_headers, employee_type="Intern")
    with_bg = [r for r in interns if r.get("internship_background")]
    if not with_bg:
        pytest.skip("no interns with a background")
    name = with_bg[0]["internship_background"]
    bg_id = next(b["id"] for b in lookups["backgrounds"] if b["name"] == name)

    result = rows(client, hr_headers, employee_type="Intern",
                  internship_background_id=bg_id)
    assert result
    for r in result:
        assert r["department"] == "Internship"
        assert r["internship_background"] == name


def test_three_filters_together(client, hr_headers, lookups):
    result = rows(client, hr_headers,
                  department_id=lookups["dept_by_name"]["Internship"],
                  employment_status="Active", employee_type="Intern")
    for r in result:
        assert r["department"] == "Internship"
        assert r["employment_status"] == "Active"


def test_filter_plus_sorting(client, hr_headers, lookups):
    dept_id = lookups["dept_by_name"]["Teaching"]
    result = rows(client, hr_headers, department_id=dept_id,
                  sort_by="full_name", sort_dir="asc")
    names = [r["full_name"] for r in result]
    assert names == sorted(names)
    assert all(r["department"] == "Teaching" for r in result)

    desc = rows(client, hr_headers, department_id=dept_id,
                sort_by="full_name", sort_dir="desc")
    assert [r["full_name"] for r in desc] == list(reversed(names))


def test_filter_plus_pagination_paginates_the_filtered_set(client, hr_headers, lookups):
    """Pagination must run on the filtered rows, not on everyone."""
    dept_id = lookups["dept_by_name"]["Internship"]
    filtered = rows(client, hr_headers, department_id=dept_id)

    response = client.get("/api/employees", headers=hr_headers,
                          params={"department_id": dept_id, "page": 1, "page_size": 2})
    body = response.json()
    assert body["meta"]["total"] == len(filtered)
    assert len(body["items"]) <= 2
    assert all(r["department"] == "Internship" for r in body["items"])

    unfiltered_total = client.get("/api/employees", headers=hr_headers,
                                  params={"page_size": 1}).json()["meta"]["total"]
    assert body["meta"]["total"] < unfiltered_total


def test_search_plus_filter_plus_pagination(client, hr_headers, lookups):
    dept_id = lookups["dept_by_name"]["Marketing"]
    response = client.get("/api/employees", headers=hr_headers, params={
        "department_id": dept_id, "search": "a", "page": 1, "page_size": 2,
        "sort_by": "full_name", "sort_dir": "asc",
    })
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) <= 2
    assert all(r["department"] == "Marketing" for r in body["items"])


def test_pages_do_not_repeat_rows_under_a_filter(client, hr_headers, lookups):
    dept_id = lookups["dept_by_name"]["Internship"]
    first = client.get("/api/employees", headers=hr_headers, params={
        "department_id": dept_id, "page": 1, "page_size": 2,
        "sort_by": "full_name", "sort_dir": "asc"}).json()["items"]
    second = client.get("/api/employees", headers=hr_headers, params={
        "department_id": dept_id, "page": 2, "page_size": 2,
        "sort_by": "full_name", "sort_dir": "asc"}).json()["items"]
    assert not ({r["id"] for r in first} & {r["id"] for r in second})


# ------------------------------------------------------------ clearing / edges
def test_clearing_filters_restores_the_full_list(client, hr_headers, lookups):
    filtered = rows(client, hr_headers,
                    department_id=lookups["dept_by_name"]["HR"],
                    employment_status="Active", search="a")
    cleared = rows(client, hr_headers)
    assert len(cleared) > len(filtered)
    assert len({r["department"] for r in cleared}) > 1


def test_empty_result_is_an_empty_page_not_an_error(client, hr_headers, lookups):
    response = client.get("/api/employees", headers=hr_headers, params={
        "department_id": lookups["dept_by_name"]["Teaching"],
        "search": "zzzznobodyhere",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["meta"]["total"] == 0


def test_unknown_department_id_returns_empty(client, hr_headers, lookups):
    assert rows(client, hr_headers, department_id=999999) == []


def test_filters_never_return_null_department_names(client, hr_headers, lookups):
    for r in rows(client, hr_headers):
        assert r["department"], "every employee row must carry a department name"
        assert r["department"] not in ("None", "null", "undefined")


def test_employee_cannot_use_the_hr_directory_filters(client, emp_a_headers):
    response = client.get("/api/employees", headers=emp_a_headers,
                          params={"employee_type": "Intern"})
    assert response.status_code == 403
